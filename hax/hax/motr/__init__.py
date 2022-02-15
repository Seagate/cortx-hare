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
from errno import EAGAIN
import logging
from typing import Any, List, Optional, Tuple
from time import sleep

from hax.consul.cache import supports_consul_cache, uses_consul_cache
from hax.exception import (BytecountException, ConfdQuorumException,
                           RepairRebalanceException)
from hax.message import (EntrypointRequest, FirstEntrypointRequest,
                         HaNvecGetEvent, HaNvecSetEvent, ProcessEvent,
                         StobIoqError)
from hax.motr.delivery import DeliveryHerald
from hax.motr.ffi import HaxFFI, make_array, make_c_str
from hax.motr.planner import WorkPlanner
from hax.types import (ByteCountStats, ConfHaProcess, Fid, FidStruct, FsStats,
                       HaLinkMessagePromise, HaNote, HaNoteStruct, HAState,
                       MessageId, ObjT, FidTypeToObjT, Profile, PverInfo,
                       ReprebStatus, ObjHealth,
                       m0HaProcessEvent, m0HaProcessType)
from hax.util import ConsulUtil, repeat_if_fails, FidWithType, PutKV

LOG = logging.getLogger('hax')

MAX_MOTR_NVEC_UPDATE_SZ = 1024


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
        def _get_rm_fid():
            return self.consul_util.get_rm_fid()

        rm_fid = _get_rm_fid()
        # Cleanup old process states.
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
            if is_first_request:
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
        # XXX Verify:
        # If rconfc from motr land sends an entrypoint request when
        # the hax consumer thread is already stopping, will posting the
        # entrypoint request to planner work if there's no one to process
        # the same?
        self.planner.add_command(EntrypointRequest(
            reply_context=reply_context,
            req_id=req_id,
            remote_rpc_endpoint=remote_rpc_endpoint,
            process_fid=process_fid,
            git_rev=git_rev,
            pid=pid,
            is_first_request=is_first_request))

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
            # Disabling dynamic fids allocation until dtm is ready to consume.
            # if util.is_proc_client(process_fid) and message.is_first_request:
            #     util.alloc_next_process_fid(process_fid)

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
                sess = util.get_leader_session()
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

            # EOS-25726: It seems that the confds were reported as started
            # and they failed later. This could be due to a Motr issue
            # EOS-25695.
            # In such a case, when processes start out of order, a wrong
            # quorum value is reported that leads to further issues in Motr
            # process startup. Thus commenting this for now. Need to verify
            # if this affects hax shutdown.
            # active_confds = []
            # if self.spiel_ready:
            #     for confd in confds:
            #         if not util.is_confd_failed(confd.fid):
            #             active_confds.append(confd)
            #     confds = active_confds

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
                          ' Replying with EAGAIN error code, with a 1'
                          ' second delay.')
            # If replied EAGAIN, motr immediately sends a subsequent entrypoint
            # request and it is observed that several entrypoint requests are
            # received by hare in a second. This floods Hare, as an
            # intermediate solution, Hare dropped the requests in case of an
            # error preparing the same. But, motr does not send any subsequent
            # entrypoint requests as expected after a timeout. As per the
            # discussion, it is agreed upon to have a temporary fix in Hare.
            # https://jts.seagate.com/browse/EOS-27068 motr ticket is created
            # to track the same.
            sleep(1)
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

    @supports_consul_cache
    def broadcast_ha_states(self,
                            ha_states: List[HAState],
                            notify_devices=True,
                            kv_cache=None,
                            broadcast_hax_only=False) -> List[MessageId]:
        LOG.debug('Broadcasting HA states %s over ha_link', ha_states)

        def _update_process_tree(proc_fid: Fid, state: ObjHealth) -> bool:
            return (st.status in (ObjHealth.FAILED, ObjHealth.OK,
                                  ObjHealth.OFFLINE) and
                    not self.consul_util.is_proc_client(st.fid) and
                    not broadcast_hax_only and
                    not self._is_mkfs(proc_fid) and
                    proc_fid != hax_fid)

        hax_fid = self.consul_util.get_hax_fid()
        notes = []
        for st in ha_states:
            if st.status == ObjHealth.UNKNOWN:
                continue
            # If its a client process then update the base fid to its full
            # fid.
            if (st.fid.container == ObjT.PROCESS.value and
                    self.consul_util.is_proc_client(st.fid)):
                proc_full_fid = self.consul_util.get_process_full_fid(st.fid)
                st.fid = proc_full_fid
            note = HaNoteStruct(st.fid.to_c(), st.status.to_ha_note_status())
            # if (st.fid.container == ObjT.PROCESS.value and
            #         self.consul_util.is_proc_client(st.fid)):
            #     proc_full_fid = self.consul_util.get_process_full_fid(st.fid)
            #     st.fid = proc_full_fid
            notes.append(note)

            # For process failure, we report failure for the corresponding
            # node (enclosure) and CVGs if all Io services are failed.
            # We avoid broadcasting for the configuration tree corresponding
            # to motr client processes, S3servers and hax, as the
            # failure of them does not affect the motr storage devices.
            # In some cases the broadcast need not be to Motr processes and
            # s3servers, e.g. for motr-mkfs processes, but the motr-mkfs
            # event still needs to be delivered to hax's motr land in-order
            # to update the hax-motr halink state. hax-motr halink is
            # established when hax responds to Motr/S3server entrypoint
            # request and terminated when Motr/S3server process notifies
            # M0_CONF_HA_PROCESS_STOPPED.
            if (st.fid.container == ObjT.PROCESS.value
                    and _update_process_tree(st.fid, st.status)):

                if st.fid.container == ObjT.PROCESS.value:
                    LOG.debug('ha_broadcast:set_process_state')
                    self.consul_util.set_process_state(st.fid, st.status)

                notes += self._generate_sub_services(note,
                                                     self.consul_util,
                                                     notify_devices,
                                                     kv_cache=kv_cache)
                # Check if we need to mark node as failed,
                # otherwise just mark controller as failed/OK
                # If we receive process failure then we will check if all IO
                # services are failed, if True then we will mark node as failed
                # If we receive process 'OK' then we will check if node is
                # not in failed state then we will mark node as OK
                # If both the above conditions are not true then we will just
                # mark controller status
                is_node_failed = self.is_node_failed(note, kv_cache=kv_cache)
                if (st.status in (ObjHealth.FAILED, ObjHealth.OFFLINE) and
                        is_node_failed):
                    notes += self.notify_node_status_by_process(
                        note, kv_cache=kv_cache)
                elif (st.status == ObjHealth.OK
                        and not is_node_failed):
                    notes += self.notify_node_status_by_process(
                        note, kv_cache=kv_cache)
                else:
                    ctrl_note = self.get_ctrl_status(note, kv_cache=kv_cache)
                    if ctrl_note is not None:
                        (a_note, updates) = ctrl_note
                        notes.append(a_note)
                        self._write_updates(updates, kv_cache)

            if st.fid.container == ObjT.DRIVE.value:
                self.consul_util.update_drive_state([st.fid],
                                                    st.status,
                                                    kv_cache=kv_cache)
            elif st.fid.container == ObjT.NODE.value:
                self.consul_util.set_node_state(st.fid,
                                                st.status,
                                                kv_cache=kv_cache)
                notes += self.add_enclosing_devices_by_node(st.fid,
                                                            st.status,
                                                            kv_cache=kv_cache)
        if not notes:
            return []
        message_ids = self._ha_broadcast(notes, broadcast_hax_only)

        return message_ids

    def _ha_broadcast(self, notes: List[HaNoteStruct],
                      broadcast_hax_only: bool) -> List[MessageId]:
        message_ids: List[MessageId] = []
        nr_notes_to_be_sent = len(notes)
        notes_sent = 0
        LOG.debug('Broadcasting %d notes', nr_notes_to_be_sent)
        while notes:
            notes_to_send = notes[0:MAX_MOTR_NVEC_UPDATE_SZ]
            notes_to_send_len = len(notes_to_send)
            notes_sent += notes_to_send_len
            if broadcast_hax_only:
                hax_endpoint = self.consul_util.get_hax_endpoint()
                message_ids = self._ffi.ha_broadcast_hax_only(
                    self._ha_ctx, make_array(HaNoteStruct, notes_to_send),
                    notes_to_send_len,
                    make_c_str(hax_endpoint))
            else:
                message_ids = self._ffi.ha_broadcast(
                    self._ha_ctx, make_array(HaNoteStruct, notes_to_send),
                    notes_to_send_len)
            LOG.debug(
                'Broadcast HA state complete, message_ids = %s',
                message_ids)
            notes = notes[MAX_MOTR_NVEC_UPDATE_SZ:]
        assert notes_sent == nr_notes_to_be_sent

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
        LOG.debug('Got ha nvec get of length %s from Motr land', len(nvec))
        self.planner.add_command(HaNvecGetEvent(hax_msg, nvec))

    @log_exception
    def ha_nvec_set(self, hax_msg: int, nvec: List[HaNote]) -> None:
        LOG.debug('Got ha nvec set of length %s from Motr land', len(nvec))
        self.planner.add_command(HaNvecSetEvent(hax_msg, nvec))

    @log_exception
    @supports_consul_cache
    def ha_nvec_get_reply(self, event: HaNvecGetEvent, kv_cache=None) -> None:
        LOG.debug('Preparing the reply for HaNvecGetEvent (nvec size = %s)',
                  len(event.nvec))
        self.consul_util.get_all_nodes()
        notes: List[HaNoteStruct] = []
        for n in event.nvec:
            fid = Fid.from_struct(n.note.no_id)
            n.note.no_state = self.consul_util.get_conf_obj_status(
                FidTypeToObjT[fid.container], fid.key, kv_cache=kv_cache)
            notes.append(n.note)

        LOG.debug('Replying ha nvec of length ' + str(len(event.nvec)))
        self._ffi.ha_nvec_reply(event.hax_msg, make_array(HaNoteStruct, notes),
                                len(notes))

    @log_exception
    def ha_nvec_set_process(self, event: HaNvecSetEvent) -> None:
        LOG.debug('Processing HaNvecSetEvent (nvec size = %s)',
                  len(event.nvec))
        self.consul_util.get_all_nodes()
        ha_states: List[HAState] = []
        bcast_ss: List[HAState] = []
        for n in event.nvec:
            fid = Fid.from_struct(n.note.no_id)
            obj_health = ObjHealth.from_ha_note_state(n.note.no_state)
            ha_states.append(HAState(fid, obj_health))
            if n.note.no_state in {HaNoteStruct.M0_NC_REPAIRED,
                                   HaNoteStruct.M0_NC_ONLINE}:
                bcast_ss.append(HAState(fid, obj_health))

            # In case of failed repair, roll back to failed state.
            elif n.note.no_state == HaNoteStruct.M0_NC_REPAIR:
                obj_health = ObjHealth.from_ha_note_state(
                                       HaNoteStruct.M0_NC_FAILED)
                bcast_ss.append(HAState(fid, obj_health))

            # In case of failed rebalance, roll back to repaired state.
            elif n.note.no_state == HaNoteStruct.M0_NC_REBALANCE:
                obj_health = ObjHealth.from_ha_note_state(
                                       HaNoteStruct.M0_NC_REPAIRED)
                bcast_ss.append(HAState(fid, obj_health))

        LOG.debug('got ha_states %s', ha_states)
        if bcast_ss:
            self.broadcast_ha_states(bcast_ss)

    @supports_consul_cache
    def _generate_sub_services(self,
                               note: HaNoteStruct,
                               cns: ConsulUtil,
                               notify_devices=True,
                               kv_cache=None) -> List[HaNoteStruct]:
        new_state = note.no_state
        fid = Fid.from_struct(note.no_id)
        service_list = cns.get_services_by_parent_process(fid,
                                                          kv_cache=kv_cache)
        LOG.debug('Process fid=%s encloses %s services as follows: %s', fid,
                  len(service_list), service_list)
        service_notes = [
            HaNoteStruct(no_id=x.fid.to_c(), no_state=new_state)
            for x in service_list
        ]
        if notify_devices:
            service_notes += self._generate_sub_disks(note, service_list, cns)
        return service_notes

    @supports_consul_cache
    def _generate_sub_disks(self,
                            note: HaNoteStruct,
                            services: List[FidWithType],
                            cns: ConsulUtil,
                            kv_cache=None) -> List[HaNoteStruct]:
        disk_list = []
        new_state = note.no_state
        proc_fid = Fid.from_struct(note.no_id)

        state = (ObjHealth.OK if new_state ==
                 HaNoteStruct.M0_NC_ONLINE else ObjHealth.OFFLINE)
        is_mkfs = self._is_mkfs(proc_fid)

        mkfs_down = is_mkfs and state != ObjHealth.OK

        if not mkfs_down:
            for svc in services:
                disk_list += cns.get_disks_by_parent_process(proc_fid, svc.fid)
        if disk_list:
            # XXX: Need to check the current state of the device, transition
            # to ONLINE only in case of an explicit request or iff the prior
            # state of the device is UNKNOWN/OFFLINE.
            if not mkfs_down:
                # We don't mark the devices as failed if the process is MKFS
                # and if its effective status is STOPPED (see EOS-24124).
                cns.update_drive_state(disk_list, state, device_event=False)
        LOG.debug('proc fid=%s encloses %d disks as follows: %s',
                  proc_fid, len(disk_list), disk_list)
        drive_ha_notes: List[HaNoteStruct] = []
        for drive_id in disk_list:
            # Get the drive state from Consul KV.
            dstate = cns.get_sdev_state(ObjT.DRIVE, drive_id.key)
            drive_ha_notes.append(HaNoteStruct(no_id=drive_id.to_c(),
                                               no_state=dstate))
        return drive_ha_notes

    @uses_consul_cache
    def _is_mkfs(self, proc_fid: Fid, kv_cache=None) -> bool:
        status = self.consul_util.get_process_status(proc_fid,
                                                     kv_cache=kv_cache)
        mkfs = m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS.name
        return status.proc_type == mkfs

    def add_node_state_by_fid(
            self,
            node_fid: Fid,
            new_state: ObjHealth
            ) -> List[HaNoteStruct]:

        # Update the node state in consul kv.
        self.consul_util.set_node_state(node_fid, new_state)

        state_int = new_state.to_ha_note_status()
        return [
            HaNoteStruct(no_id=node_fid.to_c(), no_state=state_int)
        ]

    @uses_consul_cache
    def add_enclosing_devices_by_node(self,
                                      node_fid: Fid,
                                      new_state: ObjHealth,
                                      node: Optional[str] = None,
                                      kv_cache=None) -> List[HaNoteStruct]:
        """
        Returns the list of HA notes with the state derived
        from the given node. The node is not included into the resulting list.
        """

        node = node or self.consul_util.get_node_name_by_fid(node_fid,
                                                             kv_cache=kv_cache)
        encl_fid = self.consul_util.get_node_encl_fid(node, kv_cache=kv_cache)
        ctrl_fids = self.consul_util.get_node_ctrl_fids(node,
                                                        kv_cache=kv_cache)
        LOG.debug('node_fid: %s encl_fid: %s ctrl_fids: %s with state: %s',
                  node_fid, encl_fid, ctrl_fids, new_state)

        state_int = new_state.to_ha_note_status()
        # Update the enclosure state based on the event.
        self.consul_util.set_encl_state(encl_fid, new_state, kv_cache=kv_cache)

        # Update the states of all the controllers as failed, in case of
        # node failure event.
        #
        if new_state == ObjHealth.FAILED and ctrl_fids:
            updates: List[PutKV] = []
            for x in ctrl_fids:
                updates += self.consul_util.get_ctrl_state_updates(
                    x, new_state, kv_cache=kv_cache)

            self._write_updates(updates, kv_cache)

        notes = []
        if encl_fid:
            notes = [
                HaNoteStruct(no_id=encl_fid.to_c(), no_state=state_int)
            ]
        if ctrl_fids:
            for x in ctrl_fids:
                ctrl_state = self.consul_util.get_ctrl_state(
                    ObjT.CONTROLLER, x.key, kv_cache=kv_cache)
                notes.append(HaNoteStruct(no_id=x.to_c(), no_state=ctrl_state))
        return notes

    def notify_node_status_by_process(self,
                                      proc_note: HaNoteStruct,
                                      kv_cache=None) -> List[HaNoteStruct]:
        # proc_note.no_state is of int type
        new_state = ObjHealth.from_ha_note_state(proc_note.no_state)
        proc_fid = Fid.from_struct(proc_note.no_id)
        assert ObjT.PROCESS.value == proc_fid.container
        LOG.debug('Notifying node status for process_fid=%s state=%s',
                  proc_fid, new_state)

        node = self.consul_util.get_process_node(proc_fid, kv_cache=kv_cache)

        updates: List[PutKV] = []
        if new_state == ObjHealth.OK:
            # Node can have multiple controllers. Node can be online, with
            # a single controller running online.
            # If we receive process 'OK', only the process state is
            # updated. So, we need to update the corresponding
            # controller state.
            ctrl_fid = self.consul_util.get_ioservice_ctrl_fid(
                proc_fid, kv_cache=kv_cache)
            if ctrl_fid:
                updates = self.consul_util.get_ctrl_state_updates(
                    ctrl_fid, new_state, kv_cache=kv_cache)

        node_fid = self.consul_util.get_node_fid(node, kv_cache=kv_cache)
        # FIXME make these two functions to return List[PutKV] so that the
        # write operations can be delayed to reuse the cache as long as
        # possible
        notes = self.add_node_state_by_fid(node_fid, new_state)
        notes += self.add_enclosing_devices_by_node(node_fid,
                                                    new_state,
                                                    node=node,
                                                    kv_cache=kv_cache)
        self._write_updates(updates, kv_cache)
        return notes

    @supports_consul_cache
    def get_ctrl_status(
            self,
            proc_note: HaNoteStruct,
            kv_cache=None) -> Optional[Tuple[HaNoteStruct, List[PutKV]]]:
        new_state = proc_note.no_state
        proc_fid = Fid.from_struct(proc_note.no_id)
        assert ObjT.PROCESS.value == proc_fid.container
        LOG.debug('Notifying ctrl status for process_fid=%s state=%s',
                  proc_fid, new_state)

        ctrl_fid = self.consul_util.get_ioservice_ctrl_fid(proc_fid,
                                                           kv_cache=kv_cache)

        if ctrl_fid:
            # Update controller state in consul kv.
            updates = self.consul_util.get_ctrl_state_updates(
                ctrl_fid,
                ObjHealth.from_ha_note_state(new_state),
                kv_cache=kv_cache)
            return (HaNoteStruct(no_id=ctrl_fid.to_c(),
                                 no_state=new_state), updates)
        return None

    # Check if all the IO services of node are failed
    @supports_consul_cache
    def is_node_failed(self, proc_note: HaNoteStruct, kv_cache=None):
        proc_fid = Fid.from_struct(proc_note.no_id)
        assert ObjT.PROCESS.value == proc_fid.container

        node = self.consul_util.get_process_node(proc_fid, kv_cache=kv_cache)

        return self.consul_util.all_io_services_failed(node, kv_cache=kv_cache)

    def notify_hax_stop(self):
        LOG.debug('Notifying hax stop')
        hax_fid = self.consul_util.get_hax_fid()
        hax_endpoint = self.consul_util.get_hax_endpoint()
        ids = self._ffi.hax_stop(self._ha_ctx, hax_fid.to_c(),
                                 make_c_str(hax_endpoint))
        self.herald.wait_for_all(HaLinkMessagePromise(ids))

    def get_filesystem_stats(self) -> FsStats:
        stats: FsStats = self._ffi.filesystem_stats_fetch(self._ha_ctx)
        if stats is None:
            raise ConfdQuorumException(
                'Confd quorum lost, filesystem statistics is unavailable')
        return stats

    def get_proc_bytecount(self, proc_fid: Fid) -> ByteCountStats:
        bytecount: ByteCountStats = self._ffi.proc_bytecount_fetch(
            self._ha_ctx, proc_fid.to_c())
        if not bytecount:
            raise BytecountException('Bytecount stats unavailable')
        LOG.debug('Bytecount status for proc fid: %s, stats =%s',
                  str(bytecount.proc_fid),
                  bytecount.pvers)
        return bytecount

    def get_pver_status(self, pver_fid: Fid) -> PverInfo:
        status: PverInfo = self._ffi.pver_status_fetch(
            self._ha_ctx, pver_fid.to_c())
        if not status:
            raise BytecountException('Pool version status unavailable')
        LOG.debug('Pver status for pver %s: %s', pver_fid, status.state)
        return status

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

    def _write_updates(self, updates: List[PutKV], kv_cache=None) -> None:
        for op in updates:
            self.consul_util.kv.kv_put(op.key, op.value, kv_cache=kv_cache)
