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
                         HaNvecSetEvent, ProcessEvent, ProcessHaEvent,
                         SnsRebalancePause, SnsRebalanceResume,
                         SnsRebalanceStart, SnsRebalanceStatus,
                         SnsRebalanceStop, SnsRepairPause, SnsRepairResume,
                         SnsRepairStart, SnsRepairStatus, SnsRepairStop,
                         StobIoqError)
from hax.exception import HAConsistencyException, NotDelivered
from hax.motr import Motr
from hax.motr.delivery import DeliveryHerald
from hax.motr.planner import WorkPlanner
from hax.queue.publish import EQPublisher, BQPublisher
from hax.types import (ConfHaProcess, HAState, HaLinkMessagePromise,
                       MessageId, ObjT, ObjHealth, StoppableThread,
                       m0HaProcessEvent, m0HaProcessType)
from hax.util import (ProcessGroup, dump_json, repeat_if_fails,
                      ha_process_events)
from hax.configmanager import ConfigManager, ConsulConfigManager
from hax.ha import get_producer


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
                 herald: DeliveryHerald, consul: ConfigManager,
                 process_groups: ProcessGroup, idx: int):
        super().__init__(target=self._do_work,
                         name=f'qconsumer-{idx}',
                         args=(planner, motr))
        self.is_stopped = False
        self.consul = consul
        self.eq_publisher = EQPublisher()
        self.bq_publisher = BQPublisher()
        self.herald = herald
        self.idx = idx
        self.process_groups = process_groups

    def stop(self) -> None:
        self.is_stopped = True

    def broadcast_process_state(self, event: ConfHaProcess):
        if event.fid == self.consul.get_hax_fid():
            event_type = m0HaProcessType.M0_CONF_HA_PROCESS_HA.name
        else:
            event_type = m0HaProcessType(event.chp_type).name
        data = {'fid': str(event.fid),
                'state': ha_process_events[event.chp_event],
                'type': event_type}
        payload = dump_json(data)
        res = self.bq_publisher.publish('PROCESS-STATE-UPDATE', payload)
        LOG.debug('PROCESS-STATE-UPDATE event JSON: %s res: %d',
                  payload, res)

    @repeat_if_fails(wait_seconds=1)
    def _update_process_status(self, p: WorkPlanner, motr: Motr,
                               event: ConfHaProcess) -> None:
        LOG.info('Updating process status: %s', event.fid)
        # If a consul-related exception appears, it will
        # be processed by repeat_if_fails.
        #
        # This thread will become blocked until that
        # intermittent error gets resolved.
        if event.chp_event in (
                m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED):

            svc_status = self.consul.processEventToObjHealth(event.chp_type,
                                                             event.chp_event)
            if (event.chp_event ==
                    m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED and
                    (event.chp_type ==
                     m0HaProcessType.M0_CONF_HA_PROCESS_M0D) and
                    self.consul.is_process_confd(event.fid) or
                    event.fid == self.consul.get_hax_fid()):
                # Explicitly broadcasting process status to ONLINE and
                # setting to M0_CONF_HA_PROCESS_DTM_RECOVERED in Consul
                # KV process state machine.
                svc_status = ObjHealth.OK
                event.chp_event = (
                    m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED)
            broadcast_hax_only = False
            if ((event.chp_type ==
                    m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS) or
                    (event.fid == self.consul.get_hax_fid())):
                broadcast_hax_only = True

            motr.broadcast_ha_states(
                [HAState(fid=event.fid, status=svc_status)],
                broadcast_hax_only=broadcast_hax_only)
        self.process_groups.process_group_lock(event.fid)
        self.consul.update_process_status(event)
        # No need to broadcast to all the nodes for mkfs operations.
        if event.chp_type != m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS:
            self.broadcast_process_state(event)
        self.process_groups.process_group_unlock(event.fid)

        # If we are receiving M0_CONF_HA_PROCESS_STARTED for M0D processes
        # then we will check if all the M0D processes on the local node are
        # started. If yes then we are going to send node online event to
        # MessageBus
        if (event.chp_event ==
                m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED):
            try:
                util: ConfigManager = ConsulConfigManager()
                producer = get_producer(util)
                if producer:
                    producer.check_and_send(parent_resource_type=ObjT.NODE,
                                            fid=event.fid,
                                            resource_status='online')
                else:
                    LOG.warning('Could not sent an event as producer'
                                ' is not available')
            except Exception as e:
                LOG.warning("Send event failed due to '%s'", e)

    @repeat_if_fails(wait_seconds=1)
    def update_process_failure(self, planner: WorkPlanner, motr: Motr,
                               ha_states: List[HAState]) -> List[HAState]:
        new_ha_states: List[HAState] = []
        proc_Health_to_status = {
            ObjHealth.OFFLINE: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ObjHealth.FAILED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ObjHealth.OK: m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED,
            ObjHealth.RECOVERING: m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED
        }
        process_group_fid: Any = None
        LOG.debug('bootstrap done')
        try:
            cns = self.consul
            self_fid = cns.get_hax_fid()
            am_i_rc = cns.am_i_rc()
            for state in ha_states:
                if state.fid.container == ObjT.PROCESS.value:
                    # No need to broadcast again for self, it is already
                    # handled as part of process startup.
                    if state.fid == self_fid:
                        continue
                    process_group_fid = state.fid
                    self.process_groups.process_group_lock(state.fid)
                    current_status = cns.get_process_current_status(
                                            state.status, state.fid)
                    # Process only failure events from Consul as happy
                    # path broadcast is covered as part of the process
                    # startup.
                    if current_status not in (ObjHealth.OFFLINE,
                                              ObjHealth.FAILED):
                        self.process_groups.process_group_unlock(state.fid)
                        continue
                    proc_status_remote = cns.get_process_status(state.fid)
                    proc_status: Any = None
                    # MKFS states are upated by the node corresponding to a
                    # given process. So we ignore notifications for mkfs
                    # processes.
                    if proc_status_remote.proc_type in (
                            'Unknown',
                            m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS.name):
                        self.process_groups.process_group_unlock(state.fid)
                        continue
                    proc_type = m0HaProcessType.str_to_Enum(
                         proc_status_remote.proc_type)
                    # Following cases are handled here,
                    # 1. Delayed consul service failure notification:
                    # -  We re-confirm the current process state before
                    #     notifying the process as offline/failed.
                    # 2. Consul reported process failure, current process
                    #    state is offline (this means the corresponding node
                    #    is online, i.e. hax and consul are online):
                    # -  So process's status in consul kv might not be updated
                    #    as the process died abruptly. In this case we handle
                    #    it as local process failure, update the process
                    #    status in consul kv and notify motr.
                    # 3. Consul reported process failure, current process
                    #    state is failed (this means the node corresponding to
                    #    the process also failed, i.e. hax and consul are no
                    #    more):
                    # -  Process's status in consul kv might not be updated as
                    #    the node went down abruptly. In this case, when
                    #    consul reports failure for corresponding node
                    #    processes, Hare verifies the node status and
                    #    accordingly Hare RC node processes the failures.
                    #    This may take some time if Consul server loose
                    #    the quorum and take time sync up the state.
                    # 4. Consul reported process failure, probably due to mkfs
                    #    process completion (m0tr mkfs and m0ds share the same
                    #    fid). which got delayed and process has starting now:
                    # -  Hare checks the current status of the process but it
                    #    is possible that the process state is not synced up
                    #    yet within the quorum. In this case, we continue
                    #    processing the failure event but once the process
                    #    starts successfully Hare will update and notify the
                    #    process state eventually.
                    # 5. For some reason Consul may report a process as
                    #    offline and subsequently report it as online, this
                    #    may happen due to intermittent monitor failure:
                    # -  Hare must handle the change in process states
                    #    accordingly in-order to maintain the eventual
                    #    consistency of the cluster state.
                    proc_status = proc_Health_to_status.get(current_status)
                    LOG.debug('current_status: %s proc_status_remote: %s',
                              current_status, proc_status_remote.proc_status)
                    if proc_status is None:
                        self.process_groups.process_group_unlock(state.fid)
                        continue
                    # If processes local hax is alive then let it process the
                    # event.
                    is_proc_local = cns.is_proc_local(state.fid)
                    if is_proc_local:
                        if (proc_status_remote.proc_status !=
                                proc_status.name):
                            proc_event = ConfHaProcess(chp_event=proc_status,
                                                       chp_type=proc_type,
                                                       chp_pid=0,
                                                       fid=state.fid)
                            cns.update_process_status(proc_event)
                            new_ha_states.append(
                                HAState(fid=state.fid,
                                        status=current_status))
                            # Let everyone in cluster know.
                            self.broadcast_process_state(proc_event)
                    elif am_i_rc:
                        # Check if process node is online
                        proc_node_status: ObjHealth = (
                            cns.get_proc_node_health(state.fid))
                        LOG.info('Process node status: %s', proc_node_status)
                        # If process node is online, we assume corresponding
                        # hax is also online. Let the local hax process it.
                        if proc_node_status == ObjHealth.OK:
                            self.process_groups.process_group_unlock(state.fid)
                            continue
                        # Revoke dynamic fid locks held if its a Hax process
                        # failure.
                        if proc_status_remote.proc_type == (
                                m0HaProcessType.M0_CONF_HA_PROCESS_HA):
                            cns.revoke_all_dynamic_fidk_lock_for(
                                state.fid)
                        # Probably process node failed, in such a
                        # case, only RC must be allowed to update
                        # the process's persistent state.
                        # Or, if the node's alive then allow the node
                        # to update the local process's state.
                        if (proc_status_remote.proc_status !=
                                proc_status.name):
                            proc_event = ConfHaProcess(chp_event=proc_status,
                                                       chp_type=proc_type,
                                                       chp_pid=0,
                                                       fid=state.fid)
                            cns.update_process_status(proc_event)
                            new_ha_states.append(
                                HAState(fid=state.fid,
                                        status=current_status))
                            self.broadcast_process_state(proc_event)
                    else:
                        LOG.debug('Skipping event for fid: %s', state.fid)
                    self.process_groups.process_group_unlock(state.fid)
                else:
                    new_ha_states.append(state)
        except Exception as e:
            if process_group_fid is not None:
                self.process_groups.process_group_unlock(process_group_fid)
            raise HAConsistencyException('failed to process ha states') from e
        return new_ha_states

    def _restart_notify(self, req: FirstEntrypointRequest,
                        motr: Motr):
        # Check process's restart count, if its the first time
        # (restart_count = 0), do not notify failure for this
        # process, else report failure.
        # Update restart count.
        # We don't want to send failure for hax and client
        # restarts, so skip them.
        restart_count = self.consul.get_proc_restart_count(
                            req.process_fid)
        if (req.process_fid != self.consul.get_hax_fid() and
                not self.consul.is_proc_client(req.process_fid)):
            if restart_count > 1:
                LOG.debug('Process restarted, broadcasting FAILED')
                proc_status = m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED
                proc_type = m0HaProcessType.M0_CONF_HA_PROCESS_M0D
                proc_event = ConfHaProcess(chp_event=proc_status,
                                           chp_type=proc_type,
                                           chp_pid=0,
                                           fid=req.process_fid)
                self.consul.update_process_status(proc_event)
                self.broadcast_process_state(proc_event)
                ids: List[MessageId] = motr.broadcast_ha_states(
                                       [
                                           HAState(fid=req.process_fid,
                                                   status=(
                                                       ObjHealth.FAILED))
                                       ],
                                       notify_devices=True,
                                       proc_skip_list=[req.process_fid])
                LOG.debug('waiting for broadcast of %s for ep: %s',
                          ids, req.remote_rpc_endpoint)
                # Wait for failure delivery.
                try:
                    self.herald.wait_for_all(HaLinkMessagePromise(ids))
                except NotDelivered:
                    pass
        self.consul.set_proc_restart_count(req.process_fid,
                                           restart_count + 1)

    def _do_work(self, planner: WorkPlanner, motr: Motr):  # noqa: MC0001
        LOG.info('Handler thread has started')

        try:
            while True:
                try:
                    LOG.debug('Waiting for the next message')

                    item = planner.get_next_command()

                    LOG.debug('Got %s message from planner', item)
                    if isinstance(item, FirstEntrypointRequest):
                        self._restart_notify(item, motr)
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
                    elif isinstance(item, ProcessHaEvent):
                        # All the events corresponding to a particular
                        # process must be processed in order.
                        # Avoid Duplicate processing of local process's
                        # HA events.
                        if not self.consul.is_proc_local(item.fid):
                            # No need to update Consul KV corresponding to
                            # the process tree. That is done by RC or the
                            # process's local hax. This is just a motr
                            # broadcast.
                            motr.broadcast_ha_states(item.states,
                                                     update_kv=False)
                            status = self.consul.objHealthToProcessEvent(
                                item.states[0].status)
                            # Account for received process status.
                            self.consul.update_process_status_local(
                                ConfHaProcess(chp_event=status,
                                              chp_type=item.proc_type,
                                              chp_pid=0,
                                              fid=item.fid))
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
                        # Check the current status of the object and
                        # broadcast accordingly.
                        ha_states = self.update_process_failure(
                            planner, motr, item.states)
                        result: List[MessageId] = motr.broadcast_ha_states(
                            ha_states)
                        ha = get_producer(self.consul)
                        if ha:
                            ha.broadcast(ha_states)
                        else:
                            LOG.warning('Could not sent an event as producer'
                                        ' is not available')
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
