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

from hax.exception import ConfdQuorumException, RepairRebalanceException
from hax.message import (EntrypointRequest, FirstEntrypointRequest,
                         HaNvecGetEvent, ProcessEvent, StobIoqError)
from hax.motr.delivery import DeliveryHerald
from hax.motr.ffi import HaxFFI, make_array, make_c_str
from hax.motr.planner import WorkPlanner
from hax.types import (ConfHaProcess, Fid, FidStruct, FsStats,
                       HaLinkMessagePromise, HaNote, HaNoteStruct, HAState,
                       MessageId, ObjT, Profile, ReprebStatus, ServiceHealth,
                       m0HaProcessEvent)
from hax.util import ConsulUtil, repeat_if_fails

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
                 planner: WorkPlanner,
                 herald: DeliveryHerald,
                 consul_util: ConsulUtil,
                 node_uuid: str = ''):
        self._ffi = ffi or HaxFFI()
        # [KN] Note that node_uuid is currently ignored by the corresponding
        # hax.c function
        self._ha_ctx = self._ffi.init_motr_api(self, make_c_str(node_uuid))
        self.planner = planner
        self.herald = herald
        self.consul_util = consul_util
        self.spiel_ready = False
        self.is_stopping = False

        if not self._ha_ctx:
            LOG.error('Cannot initialize Motr API. m0_halon_interface_init'
                      ' returned 0')
            raise RuntimeError('Cannot initialize Motr API')

    def start(self, rpc_endpoint: str, process: Fid, ha_service: Fid,
              profile: Profile):
        LOG.debug('Starting m0_halon_interface')
        self._process_fid = process
        self._profile = profile

        @repeat_if_fails()
        def _get_rm_fid() -> Fid:
            return self.consul_util.get_rm_fid()

        rm_fid = _get_rm_fid()
        result = self._ffi.start(self._ha_ctx, make_c_str(rpc_endpoint),
                                 process.to_c(), ha_service.to_c(),
                                 rm_fid.to_c())
        if result:
            LOG.error(
                'Cannot start Motr API. m0_halon_interface::start'
                ' returned non-zero code (%s)', result)
            raise RuntimeError('Cannot start m0_halon_interface.'
                               'Please check Motr logs for more details.')

    def start_rconfc(self) -> int:
        LOG.debug('Starting rconfc')
        profile_fid: Fid = self._profile.fid
        result: int = self._ffi.start_rconfc(self._ha_ctx, profile_fid.to_c())
        if result:
            raise RuntimeError('Cannot start rconfc.'
                               ' Please check Motr logs for more details.')
        LOG.debug('rconfc started')
        return result

    def stop(self):
        LOG.info('Stopping motr')
        self.is_stopping = True
        self.notify_hax_stop()
        if self.is_spiel_ready():
            self.stop_rconfc()
        self._ffi.motr_stop(self._ha_ctx)

    def fini(self):
        LOG.info('Finalizing motr')
        self._ffi.motr_fini(self._ha_ctx)
        self._ha_ctx = 0
        LOG.debug('Motr API context is down. Bye!')

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

    def is_spiel_ready(self):
        return self.spiel_ready

    @log_exception
    def _entrypoint_request_cb(self, reply_context: Any, req_id: Any,
                               remote_rpc_endpoint: str, process_fid: Fid,
                               git_rev: str, pid: int, is_first_request: bool):
        LOG.debug('Received entrypoint request from remote endpoint'
                  " '{}', process fid = {}".format(remote_rpc_endpoint,
                                                   str(process_fid)) +
                  ' The request will be processed in another thread.')
        try:
            if (is_first_request
                    and (not self.consul_util.is_proc_client(process_fid))):
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
                self.planner.add_command(
                    FirstEntrypointRequest(
                        reply_context=reply_context,
                        req_id=req_id,
                        remote_rpc_endpoint=remote_rpc_endpoint,
                        process_fid=process_fid,
                        git_rev=git_rev,
                        pid=pid,
                        is_first_request=is_first_request))
                return
        except Exception:
            LOG.exception('Failed to notify failure for %s', process_fid)

        LOG.debug('enqueue entrypoint request for %s', remote_rpc_endpoint)
        entrypoint_req: EntrypointRequest = EntrypointRequest(
            reply_context=reply_context,
            req_id=req_id,
            remote_rpc_endpoint=remote_rpc_endpoint,
            process_fid=process_fid,
            git_rev=git_rev,
            pid=pid,
            is_first_request=is_first_request)

        # If rconfc from motr land sends an entrypoint request when
        # the hax consumer thread is already stopping, there's no
        # point in en-queueing the request as there's no one to process
        # the same. Thus, invoke send_entrypoint_reply directly.
        self.send_entrypoint_request_reply(entrypoint_req)

    def send_entrypoint_request_reply(self, message: EntrypointRequest):
        reply_context = message.reply_context
        req_id = message.req_id
        remote_rpc_endpoint = message.remote_rpc_endpoint
        process_fid = message.process_fid
        e_rc = EAGAIN

        LOG.debug('Processing entrypoint request from remote endpoint'
                  " '{}', process fid {}".format(remote_rpc_endpoint,
                                                 str(process_fid)))
        sess = principal_rm = confds = None
        try:
            util = self.consul_util
            # When stopping, there's a possibility that hax may receive
            # an entrypoint request from motr land. In order to unblock
            # motr land, reply with entrypoint request with no confds
            # and RM endpoints as the processes might have already
            # stopped.
            rc_quorum = 0
            rm_fid = Fid(0, 0)
            if self.is_stopping:
                confds = []
            else:
                sess = util.get_leader_session_no_wait()
                principal_rm = util.get_session_node(sess)
                confds = util.get_confd_list()

            # Hax may receive entrypoint requests multiple times during its
            # lifetime. Hax starts motr rconfc to invoke spiel commands. Motr
            # rconfc establishes connection with principal RM, in case of
            # principal RM failure, rconfc invalidates its confc and again
            # requests entrypoint in a hope that there will be another confd
            # and principal RM elected so that rconfc can resume its
            # functionality. During shutdown, when each motr process stops,
            # including confds, hax broadcasts M0_NC_FAILED event for every
            # STOPPED or FAILED motr process. Motr rconfc on receiving the
            # failed events for confds, goes re-requests entrypoint information
            # and this goes on in a loop. In order to break this loop, the
            # the entrypoint reply must only report alive confds and rm
            # endpoints. While doing this we need to handle the bootstrapping
            # case, so we wait until bootstrapping is done that is all the
            # motr services are up, we check the confd status and exclude
            # corresponding confd from the entrypoint reply.
            active_confds = []
            if self.spiel_ready:
                for confd in confds:
                    if not util.is_confd_failed(confd.fid):
                        active_confds.append(confd)
                confds = active_confds

            if confds:
                rm_fid = util.get_rm_fid()
                rc_quorum = int(len(confds) / 2 + 1)
            rm_eps = None
            for svc in confds:
                if svc.node == principal_rm:
                    rm_eps = svc.address
                    break
            if confds and (not self.is_stopping) and (not rm_eps):
                if util.m0ds_stopping():
                    e_rc = 0
                raise RuntimeError('No RM node found in Consul')
        except Exception:
            LOG.exception('Failed to get the data from Consul.'
                          ' Replying with EAGAIN error code.')
            self._ffi.entrypoint_reply(reply_context, req_id.to_c(), e_rc, 0,
                                       make_array(FidStruct, []),
                                       make_array(c.c_char_p, []), 0,
                                       Fid(0, 0).to_c(), None)
            LOG.debug('Reply sent')
            return

        confd_fids = [x.fid.to_c() for x in confds]
        confd_eps = [make_c_str(x.address) for x in confds]

        LOG.debug('Passing the entrypoint reply to hax.c layer')
        self._ffi.entrypoint_reply(reply_context, req_id.to_c(), 0,
                                   len(confds),
                                   make_array(FidStruct, confd_fids),
                                   make_array(c.c_char_p,
                                              confd_eps), rc_quorum,
                                   rm_fid.to_c(), make_c_str(rm_eps))
        LOG.debug('Entrypoint request has been replied to')

    def broadcast_ha_states(self,
                            ha_states: List[HAState],
                            notify_devices=True) -> List[MessageId]:
        LOG.debug('Broadcasting HA states %s over ha_link', ha_states)

        def ha_obj_state(st):
            return HaNoteStruct.M0_NC_ONLINE if st.status == ServiceHealth.OK \
                else HaNoteStruct.M0_NC_FAILED

        notes = []
        for st in ha_states:
            if st.status in (ServiceHealth.UNKNOWN, ServiceHealth.OFFLINE):
                continue
            note = HaNoteStruct(st.fid.to_c(), ha_obj_state(st))
            notes.append(note)
            if (st.fid.container == ObjT.PROCESS.value
                    and st.status == ServiceHealth.STOPPED):
                notify_devices = False
            notes += self._generate_sub_services(note, self.consul_util,
                                                 notify_devices)
            # For process failure, we report failure for the corresponding
            # node (enclosure) and CVGs.
            if (st.fid.container == ObjT.PROCESS.value
                    and st.status in (ServiceHealth.FAILED, ServiceHealth.OK)):
                notes += self.notify_node_status(note)
            if st.fid.container == ObjT.DRIVE.value:
                self.consul_util.update_drive_state([st.fid], st.status)
        if not notes:
            return []
        message_ids: List[MessageId] = self._ffi.ha_broadcast(
            self._ha_ctx, make_array(HaNoteStruct, notes), len(notes))
        LOG.debug(
            'Broadcast HA state complete with the following message_ids = %s',
            message_ids)
        return message_ids

    def _process_event_cb(self, fid, chp_event, chp_type, chp_pid):
        LOG.info('fid=%s, chp_event=%s', fid, chp_event)
        self.planner.add_command(
            ProcessEvent(
                ConfHaProcess(chp_event=chp_event,
                              chp_type=chp_type,
                              chp_pid=chp_pid,
                              fid=fid)))

        if chp_event == m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED:
            proc_ep = self.consul_util.fid_to_endpoint(fid)
            if proc_ep:
                self._ffi.hax_link_stopped(self._ha_ctx, make_c_str(proc_ep))

    def _stob_ioq_event_cb(self, fid, sie_conf_sdev, sie_stob_id, sie_fd,
                           sie_opcode, sie_rc, sie_offset, sie_size,
                           sie_bshift):
        LOG.info('fid=%s, sie_conf_sdev=%s', fid, sie_conf_sdev)
        self.planner.add_command(
            StobIoqError(fid, sie_conf_sdev, sie_stob_id, sie_fd, sie_opcode,
                         sie_rc, sie_offset, sie_size, sie_bshift))

    def _msg_delivered_cb(self, proc_fid, proc_endpoint: str, tag: int,
                          halink_ctx: int):
        LOG.info(
            'Delivered to endpoint'
            "'{}', process fid = {}".format(proc_endpoint, str(proc_fid)) +
            'tag= %d', tag)
        self.herald.notify_delivered(MessageId(halink_ctx=halink_ctx, tag=tag))

    def _msg_not_delivered_cb(self, proc_fid, proc_endpoint: str, tag: int,
                              halink_ctx: int):
        LOG.info(
            'Message delivery failed, endpoint'
            "'{}', process fid = {}".format(proc_endpoint, str(proc_fid)) +
            'tag= %d', tag)
        self.herald.notify_delivered(MessageId(halink_ctx=halink_ctx, tag=tag))

    @log_exception
    def ha_nvec_get(self, hax_msg: int, nvec: List[HaNote]) -> None:
        LOG.debug('Got ha nvec of length %s from Motr land', len(nvec))
        self.planner.add_command(HaNvecGetEvent(hax_msg, nvec))

    @log_exception
    def ha_nvec_get_reply(self, event: HaNvecGetEvent) -> None:
        LOG.debug('Preparing the reply for HaNvecGetEvent (nvec size = %s)',
                  len(event.nvec))
        notes: List[HaNoteStruct] = []
        for n in event.nvec:
            n.note.no_state = HaNoteStruct.M0_NC_ONLINE
            if (n.obj_t in (ObjT.PROCESS.name, ObjT.SERVICE.name)):
                n.note.no_state = self.consul_util.get_conf_obj_status(
                    ObjT[n.obj_t], n.note.no_id.f_key)
            notes.append(n.note)

        LOG.debug('Replying ha nvec of length ' + str(len(event.nvec)))
        self._ffi.ha_nvec_reply(event.hax_msg, make_array(HaNoteStruct, notes),
                                len(notes))

    def _generate_sub_services(self,
                               note: HaNoteStruct,
                               cns: ConsulUtil,
                               notify_devices=True) -> List[HaNoteStruct]:
        new_state = note.no_state
        fid = Fid.from_struct(note.no_id)
        service_list = cns.get_services_by_parent_process(fid)
        LOG.debug('Process fid=%s encloses %s services as follows: %s', fid,
                  len(service_list), service_list)
        service_notes = [
            HaNoteStruct(no_id=x.fid.to_c(), no_state=new_state)
            for x in service_list
        ]
        if notify_devices:
            service_notes += self._generate_sub_disks(note, service_list, cns)
        return service_notes

    def _generate_sub_disks(self, note: HaNoteStruct, services: List,
                            cns: ConsulUtil) -> List[HaNoteStruct]:
        disk_list = []
        new_state = note.no_state
        proc_fid = Fid.from_struct(note.no_id)
        for svc in services:
            disk_list += cns.get_disks_by_parent_process(proc_fid, svc.fid)
        LOG.debug('proc fid=%s encloses %d disks with state %d as follows: %s',
                  proc_fid, len(disk_list), int(new_state), disk_list)
        if disk_list:
            state = (ServiceHealth.OK if new_state ==
                     HaNoteStruct.M0_NC_ONLINE else ServiceHealth.FAILED)
            # XXX: Need to check the current state of the device, transition
            # to ONLINE only in case of an explicit request or iff the prior
            # state of the device is UNKNOWN/OFFLINE.
            cns.update_drive_state(disk_list, state, device_event=False)
        return [
            HaNoteStruct(no_id=x.to_c(), no_state=new_state) for x in disk_list
        ]

    def notify_node_status(self,
                           proc_note: HaNoteStruct) -> List[HaNoteStruct]:
        new_state = proc_note.no_state
        proc_fid = Fid.from_struct(proc_note.no_id)
        assert ObjT.PROCESS.value == proc_fid.container
        LOG.debug('Notifying node status for process_fid=%s state=%s',
                  proc_fid, new_state)

        node = self.consul_util.get_process_node(proc_fid)

        node_fid = self.consul_util.get_node_fid(node)
        encl_fid = self.consul_util.get_node_encl_fid(node)
        ctrl_fid = self.consul_util.get_node_ctrl_fid(node)
        LOG.debug('node_fid: %s encl_fid: %s ctrl_fid: %s with state: %s',
                  node_fid, encl_fid, ctrl_fid, new_state)

        notes = []
        if node_fid and encl_fid and ctrl_fid:
            notes = [HaNoteStruct(no_id=x.to_c(), no_state=new_state)
                     for x in [node_fid, encl_fid, ctrl_fid]]

        return notes

    def notify_hax_stop(self):
        LOG.debug('Notifying hax stop')
        hax_fid = self.consul_util.get_hax_fid()
        hax_endpoint = self.consul_util.get_hax_endpoint()
        ids = self._ffi.hax_stop(self._ha_ctx, hax_fid.to_c(),
                                 make_c_str(hax_endpoint))
        self.herald.wait_for_all(HaLinkMessagePromise(ids))

    def adopt_motr_thread(self):
        LOG.debug('Adopting Motr thread')
        self._ffi.adopt_motr_thread(self._ha_ctx)

    def shun_motr_thread(self):
        LOG.debug('Shunning Motr thread')
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
