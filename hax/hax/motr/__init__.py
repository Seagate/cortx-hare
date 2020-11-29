# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#

import ctypes as c
import logging
from errno import EAGAIN
from typing import Any, List
# from queue import Queue

from hax.exception import ConfdQuorumException, RepairRebalanceException
from hax.message import (BroadcastHAStates, EntrypointRequest, HaNvecGetEvent,
                         ProcessEvent)
from hax.motr.delivery import DeliveryHerald
from hax.motr.ffi import HaxFFI, make_array, make_c_str
from hax.types import (ConfHaProcess, Fid, FidStruct, FsStats, HaNote,
                       HaNoteStruct, HAState, MessageId, ObjT, ReprebStatus,
                       StobIoqError, ServiceHealth, m0HaProcessEvent,
                       m0HaProcessType, HaLinkMessagePromise)
from hax.util import ConsulUtil

LOG = logging.getLogger('hax')


def log_exception(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            LOG.exception('**ERROR**')

    return wrapper


class Motr:
    def __init__(self,
                 ffi: HaxFFI,
                 queue,
                 rm_fid: Fid,
                 herald: DeliveryHerald,
                 consul_util: ConsulUtil,
                 node_uuid: str = ''):
        self._ffi = ffi or HaxFFI()
        # [KN] Note that node_uuid is currently ignored by the corresponding
        # hax.c function
        self._ha_ctx = self._ffi.init_motr_api(self, make_c_str(node_uuid))
        self.queue = queue
        self.rm_fid = rm_fid
        self.herald = herald
        self.consul_util = consul_util

        if not self._ha_ctx:
            LOG.error('Cannot initialize Motr API. m0_halon_interface_init'
                      ' returned 0')
            raise RuntimeError('Cannot initialize Motr API')

    def start(self, rpc_endpoint: str, process: Fid, ha_service: Fid,
              rm_service: Fid):
        LOG.debug('Starting m0_halon_interface')
        self._process_fid = process
        result = self._ffi.start(self._ha_ctx, make_c_str(rpc_endpoint),
                                 process.to_c(), ha_service.to_c(),
                                 rm_service.to_c())
        if result:
            LOG.error(
                'Cannot start Motr API. m0_halon_interface::start'
                ' returned non-zero code (%s)', result)
            raise RuntimeError('Cannot start m0_halon_interface.'
                               'Please check Motr logs for more details.')

    def start_rconfc(self) -> int:
        LOG.debug('Starting rconfc')
        result: int = self._ffi.start_rconfc(self._ha_ctx,
                                             self._process_fid.to_c())
        if result:
            raise RuntimeError('Cannot start rconfc.'
                               ' Please check Motr logs for more details.')
        LOG.debug('rconfc started')
        return result

    def stop_rconfc(self) -> int:
        LOG.debug('Stopping rconfc')
        result: int = self._ffi.stop_rconfc(self._ha_ctx)
        if result:
            LOG.error(
                'Cannot stop rconfc. rconfc stop operation'
                'returned non-zero code (%s)', result)
            raise RuntimeError('Cannot stop rconfc.'
                               'Please check Motr logs for more details.')
        LOG.debug('confc has been stopped successfuly')
        return result

    @log_exception
    def _entrypoint_request_cb(self, reply_context: Any, req_id: Any,
                               remote_rpc_endpoint: str, process_fid: Fid,
                               git_rev: str, pid: int, is_first_request: bool):
        LOG.debug('Received entrypoint request from remote endpoint'
                  " '{}', process fid = {}".format(remote_rpc_endpoint,
                                                   str(process_fid)) +
                  ' The request will be processed in another thread.')
        try:
            if (is_first_request and
                    (not self.consul_util.is_proc_client(process_fid))):
                # This is the first start of this process or the process has
                # restarted.
                # Let everyone know that the process has restarted so that
                # they can re-establish their connections with the process.
                # Disconnect all the halinks this process is any.
                # Motr clients are filtered out as they are the initiators of
                # the rpc connections to motr ioservices. Presently there's no
                # need identified to report motr client restarts, Consul will
                # anyway detect the failure and report the same so we exclude
                # reporting the same during their first entrypoint request.
                # But we need to do it for motr server processes.
                # q: Queue = Queue(1)
                LOG.debug('first entrypoint request, broadcasting FAILED')
                states = [HAState(fid=process_fid,
                                  status=ServiceHealth.FAILED)]
                LOG.info('HA states: %s', states)
                ids: List[MessageId] = self.broadcast_ha_states(states)
                LOG.debug('waiting for broadcast of %s ep: %s',
                          ids, remote_rpc_endpoint)
                self.herald.wait_for_all(HaLinkMessagePromise(ids))
        except Exception:
            pass

        LOG.debug('enqueue entrypoint request for %s',
                  remote_rpc_endpoint)
        self.queue.put(
            EntrypointRequest(
                reply_context=reply_context,
                req_id=req_id,
                remote_rpc_endpoint=remote_rpc_endpoint,
                process_fid=process_fid,
                git_rev=git_rev,
                pid=pid,
                is_first_request=is_first_request,
            ))

    def send_entrypoint_request_reply(self, message: EntrypointRequest):
        reply_context = message.reply_context
        req_id = message.req_id
        remote_rpc_endpoint = message.remote_rpc_endpoint
        process_fid = message.process_fid

        LOG.debug('Processing entrypoint request from remote endpoint'
                  " '{}', process fid {}".format(remote_rpc_endpoint,
                                                 str(process_fid)))
        sess = principal_rm = confds = None
        try:
            prov = self.consul_util
            sess = prov.get_leader_session_no_wait()
            principal_rm = prov.get_session_node(sess)
            confds = prov.get_confd_list()
        except Exception:
            LOG.exception('Failed to get the data from Consul.'
                          ' Replying with EAGAIN error code.')
            self._ffi.entrypoint_reply(reply_context, req_id.to_c(), EAGAIN, 0,
                                       make_array(FidStruct, []),
                                       make_array(c.c_char_p, []), 0,
                                       self.rm_fid.to_c(), None)
            LOG.debug('Reply sent')
            return

        rc_quorum = int(len(confds) / 2 + 1)

        rm_eps = None
        for svc in confds:
            if svc.node == principal_rm:
                rm_eps = svc.address
                break
        if not rm_eps:
            raise RuntimeError('No RM node found in Consul')

        confd_fids = [x.fid.to_c() for x in confds]
        confd_eps = [make_c_str(x.address) for x in confds]

        LOG.debug('Passing the entrypoint reply to hax.c layer')
        self._ffi.entrypoint_reply(reply_context, req_id.to_c(), 0,
                                   len(confds),
                                   make_array(FidStruct, confd_fids),
                                   make_array(c.c_char_p,
                                              confd_eps), rc_quorum,
                                   self.rm_fid.to_c(), make_c_str(rm_eps))
        LOG.debug('Entrypoint request has been replied to')

    def broadcast_ha_states(self, ha_states: List[HAState]) -> List[MessageId]:
        LOG.debug('Broadcasting HA states %s over ha_link', ha_states)

        def ha_obj_state(st):
            return HaNoteStruct.M0_NC_ONLINE if st.status == ServiceHealth.OK \
                else HaNoteStruct.M0_NC_FAILED

        notes = []
        for st in ha_states:
            note = HaNoteStruct(st.fid.to_c(), ha_obj_state(st))
            notes.append(note)
            notes += self._generate_sub_services(note, self.consul_util)

        message_ids: List[MessageId] = self._ffi.ha_broadcast(
            self._ha_ctx, make_array(HaNoteStruct, notes), len(notes))
        LOG.debug(
            'Broadcast HA state complete with the following message_ids = %s',
            message_ids)
        return message_ids

    def _process_event_cb(self, fid, chp_event, chp_type, chp_pid):
        LOG.info('fid=%s, chp_event=%s', fid, chp_event)
        self.queue.put(
            ProcessEvent(
                ConfHaProcess(chp_event=chp_event,
                              chp_type=chp_type,
                              chp_pid=chp_pid,
                              fid=fid)))

        if chp_type == m0HaProcessType.M0_CONF_HA_PROCESS_M0D:
            if chp_event == m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED:
                self.queue.put(
                    BroadcastHAStates(
                        states=[HAState(fid=fid, status=ServiceHealth.OK)],
                        reply_to=None))

    def _stob_ioq_event_cb(self, fid, sie_conf_sdev, sie_stob_id, sie_fd,
                           sie_opcode, sie_rc, sie_offset, sie_size,
                           sie_bshift):
        LOG.info('fid=%s, sie_conf_sdev=%s', fid, sie_conf_sdev)
        self.queue.put(
            StobIoqError(fid, sie_conf_sdev, sie_stob_id, sie_fd, sie_opcode,
                         sie_rc, sie_offset, sie_size, sie_bshift))

    def _msg_delivered_cb(self, proc_fid, proc_endpoint: str, tag: int,
                          halink_ctx: int):
        LOG.info(
            'Delivered to endpoint'
            "'{}', process fid = {}".format(proc_endpoint, str(proc_fid)) +
            'tag= %d', tag)
        self.herald.notify_delivered(MessageId(halink_ctx=halink_ctx, tag=tag))

    @log_exception
    def ha_nvec_get(self, hax_msg: int, nvec: List[HaNote]) -> None:
        LOG.debug('Got ha nvec of length %s from Motr land', len(nvec))
        self.queue.put(HaNvecGetEvent(hax_msg, nvec))

    @log_exception
    def ha_nvec_get_reply(self, event: HaNvecGetEvent) -> None:
        LOG.debug('Preparing the reply for HaNvecGetEvent (nvec size = %s)',
                  len(event.nvec))
        notes: List[HaNoteStruct] = []
        for n in event.nvec:
            n.note.no_state = HaNoteStruct.M0_NC_ONLINE
            if (n.obj_t in (ObjT.PROCESS.name, ObjT.SERVICE.name) and
                self.consul_util.get_conf_obj_status(ObjT[n.obj_t],
                                                     n.note.no_id.f_key) !=
                    'passing'):
                n.note.no_state = HaNoteStruct.M0_NC_FAILED
            notes.append(n.note)

        LOG.debug('Replying ha nvec of length ' + str(len(event.nvec)))
        self._ffi.ha_nvec_reply(event.hax_msg, make_array(HaNoteStruct, notes),
                                len(notes))

    def _generate_sub_services(self, note: HaNoteStruct,
                               cns: ConsulUtil) -> List[HaNoteStruct]:
        new_state = note.no_state
        fid = Fid.from_struct(note.no_id)
        service_list = cns.get_services_by_parent_process(fid)
        LOG.debug('Process fid=%s encloses %s services as follows: %s', fid,
                  len(service_list), service_list)
        return [
            HaNoteStruct(no_id=x.fid.to_c(), no_state=new_state)
            for x in service_list
        ]

    def close(self):
        LOG.debug('Shutting down Motr API')
        self._ffi.destroy(self._ha_ctx)
        self._ha_ctx = 0
        LOG.debug('Motr API context is down. Bye!')

    def adopt_motr_thread(self):
        LOG.debug('Adopting Motr thread')
        self._ffi.adopt_motr_thread()

    def shun_motr_thread(self):
        self._ffi.shun_motr_thread()

    def get_filesystem_stats(self) -> FsStats:
        stats: FsStats = self._ffi.filesystem_stats_fetch(self._ha_ctx)
        if stats is None:
            raise ConfdQuorumException(
                'Confd quorum lost, filesystem statistics is unavailable')
        return stats

    def get_repair_status(self, pool_fid: Fid) -> List[ReprebStatus]:
        LOG.debug('Fetching repair status for pool %s', pool_fid)
        status: List[ReprebStatus] = self._ffi.repair_status(
            self._ha_ctx, pool_fid.to_c())
        if status is None:
            raise RepairRebalanceException('Repair status unavailable')
        LOG.debug('Repair status for pool %s: %s', pool_fid, status)
        return status

    def get_rebalance_status(self, pool_fid: Fid) -> List[ReprebStatus]:
        LOG.debug('Fetching rebalance status for pool %s', pool_fid)
        status: List[ReprebStatus] = self._ffi.rebalance_status(
            self._ha_ctx, pool_fid.to_c())
        if status is None:
            raise RepairRebalanceException('rebalance status unavailable')
        LOG.debug('rebalance status for pool %s: %s', pool_fid, status)
        return status

    def start_repair(self, pool_fid: Fid):
        LOG.debug('Initiating repair for pool %s', pool_fid)
        result: int = self._ffi.start_repair(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_repair_start", please' +
                ' check Motr logs for more details.')
        LOG.debug('Repairing started for pool %s', pool_fid)

    def start_rebalance(self, pool_fid: Fid):
        LOG.debug('Initiating rebalance for pool %s', pool_fid)
        result: int = self._ffi.start_rebalance(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_rebalance_start",' +
                'please check Motr logs for more details.')
        LOG.debug('Rebalancing started for pool %s', pool_fid)

    def stop_repair(self, pool_fid: Fid):
        LOG.debug('Stopping repair for pool %s', pool_fid)
        result: int = self._ffi.stop_repair(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_repair_stop", please' +
                ' check Motr logs for more details.')
        LOG.debug('Repairing stoped for pool %s', pool_fid)

    def stop_rebalance(self, pool_fid: Fid):
        LOG.debug('Stopping rebalance for pool %s', pool_fid)
        result: int = self._ffi.stop_rebalance(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_rebalance_stop",' +
                'please check Motr logs for more details.')
        LOG.debug('Rebalancing stoped for pool %s', pool_fid)

    def pause_repair(self, pool_fid: Fid):
        LOG.debug('Pausing repair for pool %s', pool_fid)
        result: int = self._ffi.pause_repair(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_repair_pause", please' +
                ' check Motr logs for more details.')
        LOG.debug('Repairing paused for pool %s', pool_fid)

    def pause_rebalance(self, pool_fid: Fid):
        LOG.debug('Pausing rebalance for pool %s', pool_fid)
        result: int = self._ffi.pause_rebalance(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_rebalance_pause",' +
                'please check Motr logs for more details.')
        LOG.debug('Rebalancing paused for pool %s', pool_fid)

    def resume_repair(self, pool_fid: Fid):
        LOG.debug('Resuming repair for pool %s', pool_fid)
        result: int = self._ffi.resume_repair(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_repair_resume",'
                'please check Motr logs for more details.')
        LOG.debug('Repairing resumed for pool %s', pool_fid)

    def resume_rebalance(self, pool_fid: Fid):
        LOG.debug('Resuming rebalance for pool %s', pool_fid)
        result: int = self._ffi.resume_rebalance(self._ha_ctx, pool_fid.to_c())
        if result:
            raise RepairRebalanceException(
                'Failed to send SPIEL request "sns_rebalance_resume",' +
                'please check Motr logs for more details.')
        LOG.debug('Rebalancing resumed for pool %s', pool_fid)
