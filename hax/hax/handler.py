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

import logging
from typing import List, Any

from hax.message import (BroadcastHAStates, Die, EntrypointRequest,
                         FirstEntrypointRequest, HaNvecGetEvent,
                         HaNvecSetEvent, ProcessEvent,
                         SnsRebalancePause, SnsRebalanceResume,
                         SnsRebalanceStart, SnsRebalanceStatus,
                         SnsRebalanceStop, SnsRepairPause, SnsRepairResume,
                         SnsRepairStart, SnsRepairStatus, SnsRepairStop,
                         StobIoqError)
from hax.motr import Motr
from hax.motr.delivery import DeliveryHerald
from hax.motr.planner import WorkPlanner
from hax.queue.publish import EQPublisher
from hax.types import (ConfHaProcess, HAState, MessageId,
                       ObjT, ObjHealth, StoppableThread, m0HaProcessEvent,
                       m0HaProcessType)
from hax.util import ConsulUtil, dump_json, repeat_if_fails

LOG = logging.getLogger('hax')


class ConsumerThread(StoppableThread):
    """
    The only Motr-aware thread in whole HaX. This thread pulls messages from
    the multithreaded Queue and considers the messages as commands. Every such
    a command describes what should be sent to Motr land.

    The thread exits gracefully when it receives message of type Die (i.e.
    it is a 'poison pill').
    """

    def __init__(self, planner: WorkPlanner, motr: Motr,
                 herald: DeliveryHerald, consul: ConsulUtil, idx: int):
        super().__init__(target=self._do_work,
                         name=f'qconsumer-{idx}',
                         args=(planner, motr))
        self.is_stopped = False
        self.consul = consul
        self.eq_publisher = EQPublisher()
        self.herald = herald
        self.idx = idx

    def stop(self) -> None:
        self.is_stopped = True

    @repeat_if_fails(wait_seconds=1)
    def _update_process_status(self, p: WorkPlanner, motr: Motr,
                               event: ConfHaProcess) -> None:
        # If a consul-related exception appears, it will
        # be processed by repeat_if_fails.
        #
        # This thread will become blocked until that
        # intermittent error gets resolved.
        motr_to_svc_status = {
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED): (
                    ObjHealth.OK),
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED): (
                    ObjHealth.FAILED),
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0D,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED): (
                    ObjHealth.OK),
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0D,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED): (
                    ObjHealth.FAILED),
            (m0HaProcessType.M0_CONF_HA_PROCESS_OTHER,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED): (
                    ObjHealth.OK),
            (m0HaProcessType.M0_CONF_HA_PROCESS_OTHER,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED): (
                    ObjHealth.FAILED)}
        if event.chp_event in (m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED,
                               m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED):
            svc_status = motr_to_svc_status[(event.chp_type, event.chp_event)]
            broadcast_hax_only = False
            if ((event.chp_type ==
                 m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS) or
               (event.fid == self.consul.get_hax_fid())):
                # Motr-mkfs processes do not require updates on their peer
                # mkfs processes. Motr-mkfs is an independent and typically a
                # one-time operation. So avoid broadcasting a motr-mkfs state
                # to the peer motr-mkfs processes but hax still needs to be
                # notified in-order to disconnect the hax-motr halink when
                # motr-mkfs process stops.
                broadcast_hax_only = True

            LOG.debug('chp_type %d broadcast_hax_only %s', event.chp_type,
                      broadcast_hax_only)
            motr.broadcast_ha_states(
                [HAState(fid=event.fid, status=svc_status)],
                broadcast_hax_only=broadcast_hax_only)
        self.consul.update_process_status(event)

    @repeat_if_fails(wait_seconds=1)
    def update_process_failure(self, planner: WorkPlanner,
                               ha_states: List[HAState]) -> List[HAState]:
        new_ha_states: List[HAState] = []
        for state in ha_states:
            if state.fid.container == ObjT.PROCESS.value:
                current_status = self.consul.get_process_current_status(
                    state.status, state.fid)
                proc_status_remote = self.consul.get_process_status(
                                         state.fid)
                proc_status: Any = None
                # MKFS states are upated by the node corresponding to a
                # given process. So we ignore notifications for mkfs
                # processes.
                if proc_status_remote.proc_type in (
                        'Unknown',
                        str(m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS)):
                    continue
                proc_type = m0HaProcessType.str_to_Enum(
                     proc_status_remote.proc_type)
                # Following cases are handled here,
                # 1. Delayed consul service failure notification:
                # -  We re-confirm the current process state before notifying
                #    the process as offline/failed.
                # 2. Consul reported process failure, current process
                #    state is offline (this means the corresponding node is
                #    online, i.e. hax and consul are online):
                # -  So process's status in consul kv might not be updated
                #    as the process died abruptly. In this case we handle it
                #    as local process failure, update the process status
                #    in consul kv and notify motr.
                # 3. Consul reported process failure, current process state is
                #    failed (this means the node corresponding to the process
                #    also failed, i.e. hax and consul are no more):
                # -  Process's status in consul kv might not be updated as the
                #    node went down abruptly. In this case, when consul reports
                #    failure for corresponding node processes, Hare verifies
                #    the node status and accordingly Hare RC node processes the
                #    failures. This may take some time if Consul server loose
                #    the quorum and take time sync up the state.
                # 4. Consul reported process failure, probably due to mkfs
                #    process completion (m0tr mkfs and m0ds share the same
                #    fid). which got delayed and process has starting now:
                # -  Hare checks the current status of the process but it is
                #    possible that the process state is not synced up yet
                #    within the quorum. In this case, we continue processing
                #    the failure event but once the process starts successfully
                #    Hare will update and notify the process state eventually.
                if ((current_status in (ObjHealth.OFFLINE,
                                        ObjHealth.FAILED) and (
                        proc_status_remote.proc_status !=
                        'M0_CONF_HA_PROCESS_STOPPED')) or
                    (current_status == ObjHealth.OK and (
                        proc_status_remote.proc_status !=
                        'M0_CONF_HA_PROCESS_STARTED'))):
                    if ((self.consul.am_i_rc() and
                            current_status == ObjHealth.FAILED) or
                            (self.consul.is_proc_local(state.fid) and
                             current_status == ObjHealth.OFFLINE)):
                        proc_status = (
                            m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED)
                    else:
                        proc_status = (
                            m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED)
                    self.consul.update_process_status(
                        ConfHaProcess(chp_event=proc_status,
                                      chp_type=proc_type,
                                      chp_pid=0,
                                      fid=state.fid))
                    new_ha_states.append(
                        HAState(fid=state.fid, status=current_status))
                if not self.consul.is_proc_local(state.fid):
                    proc_status_local = self.consul.get_process_status_local(
                                            state.fid)
                    # Consul monitors a process every 1 second and this
                    # notification is sent to every node. Thus to avoid
                    # notifying about a process multiple times about the
                    # same status every node maintains a local copy of the
                    # remote process status, which is checked everytime a
                    # consul notification is received and accordingly
                    # the status is notified locally to all the local motr
                    # processes.
                    if (current_status == ObjHealth.OK and
                            (proc_status_local.proc_status !=
                             'M0_CONF_HA_PROCESS_STARTED')):
                        proc_status = (
                            m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED)
                    elif current_status in (ObjHealth.OFFLINE,
                                            ObjHealth.FAILED):
                        if (proc_status_local.proc_status !=
                                'M0_CONF_HA_PROCESS_STOPPED'):
                            proc_status = (
                                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED)
                    else:
                        continue
                    if proc_status is not None:
                        self.consul.update_process_status_local(
                            ConfHaProcess(chp_event=proc_status,
                                          chp_type=proc_type,
                                          chp_pid=0,
                                          fid=state.fid))
                        new_ha_states.append(
                            HAState(fid=state.fid, status=current_status))
            else:
                new_ha_states.append(state)
        return new_ha_states

    def _do_work(self, planner: WorkPlanner, motr: Motr):
        LOG.info('Handler thread has started')

        try:
            while True:
                try:
                    LOG.debug('Waiting for the next message')

                    item = planner.get_next_command()

                    LOG.debug('Got %s message from planner', item)
                    if isinstance(item, FirstEntrypointRequest):
                        motr.send_entrypoint_request_reply(
                            EntrypointRequest(
                                reply_context=item.reply_context,
                                req_id=item.req_id,
                                remote_rpc_endpoint=item.remote_rpc_endpoint,
                                process_fid=item.process_fid,
                                git_rev=item.git_rev,
                                pid=item.pid,
                                is_first_request=item.is_first_request))
                    elif isinstance(item, EntrypointRequest):
                        # While replying any Exception is catched. In such a
                        # case, the motr process will receive EAGAIN and
                        # hence will need to make new attempt by itself
                        motr.send_entrypoint_request_reply(item)
                    elif isinstance(item, ProcessEvent):
                        self._update_process_status(planner, motr, item.evt)
                    elif isinstance(item, HaNvecGetEvent):
                        fn = motr.ha_nvec_get_reply
                        # If a consul-related exception appears, it will
                        # be processed by repeat_if_fails.
                        #
                        # This thread will become blocked until that
                        # intermittent error gets resolved.
                        decorated = (repeat_if_fails(wait_seconds=5))(fn)
                        decorated(item)
                    elif isinstance(item, HaNvecSetEvent):
                        fn = motr.ha_nvec_set_process
                        # If a consul-related exception appears, it will
                        # be processed by repeat_if_fails.
                        #
                        # This thread will become blocked until that
                        # intermittent error gets resolved.
                        decorated = (repeat_if_fails(wait_seconds=5))(fn)
                        decorated(item)
                    elif isinstance(item, BroadcastHAStates):
                        LOG.info('HA states: %s', item.states)
                        ha_states = self.update_process_failure(
                            planner, item.states)
                        result: List[MessageId] = motr.broadcast_ha_states(
                            ha_states)
                        if item.reply_to:
                            item.reply_to.put(result)
                    elif isinstance(item, StobIoqError):
                        LOG.info('Stob IOQ: %s', item.fid)
                        payload = dump_json(item)
                        LOG.debug('Stob IOQ JSON: %s', payload)
                        offset = self.eq_publisher.publish('stob-ioq', payload)
                        LOG.debug('Written to epoch: %s', offset)
                    elif isinstance(item, SnsRepairStatus):
                        LOG.info('Requesting SNS repair status')
                        status = motr.get_repair_status(item.fid)
                        LOG.info('SNS repair status is received: %s', status)
                        item.reply_to.put(status)
                    elif isinstance(item, SnsRebalanceStatus):
                        LOG.info('Requesting SNS rebalance status')
                        status = motr.get_rebalance_status(item.fid)
                        LOG.info('SNS rebalance status is received: %s',
                                 status)
                        item.reply_to.put(status)
                    elif isinstance(item, SnsRebalanceStart):
                        LOG.info('Requesting SNS rebalance start')
                        motr.start_rebalance(item.fid)
                    elif isinstance(item, SnsRebalanceStop):
                        LOG.info('Requesting SNS rebalance stop')
                        motr.stop_rebalance(item.fid)
                    elif isinstance(item, SnsRebalancePause):
                        LOG.info('Requesting SNS rebalance pause')
                        motr.pause_rebalance(item.fid)
                    elif isinstance(item, SnsRebalanceResume):
                        LOG.info('Requesting SNS rebalance resume')
                        motr.resume_rebalance(item.fid)
                    elif isinstance(item, SnsRepairStart):
                        LOG.info('Requesting SNS repair start')
                        motr.start_repair(item.fid)
                    elif isinstance(item, SnsRepairStop):
                        LOG.info('Requesting SNS repair stop')
                        motr.stop_repair(item.fid)
                    elif isinstance(item, SnsRepairPause):
                        LOG.info('Requesting SNS repair pause')
                        motr.pause_repair(item.fid)
                    elif isinstance(item, SnsRepairResume):
                        LOG.info('Requesting SNS repair resume')
                        motr.resume_repair(item.fid)
                    elif isinstance(item, Die):
                        raise StopIteration()
                    else:
                        LOG.warning('Unsupported event type received: %s',
                                    item)
                except StopIteration:
                    raise
                except Exception:
                    # no op, swallow the exception
                    LOG.exception('**ERROR**')
                finally:
                    planner.notify_finished(item)
        except StopIteration:
            LOG.info('Consumer Stopped')
            if self.idx == 0:
                motr.stop()
        finally:
            LOG.info('Handler thread has exited')
