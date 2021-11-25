# Copyright (c) 2021 Seagate Technology LLC and/or its Affiliates
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
from typing import Callable, Dict, List, Tuple

from hax.motr.workflow import Context, ObjectWorkflow
from hax.types import Fid, ServiceHealth, m0HaObjState

from .action import Action, BroadcastState, SetObjectStatus
from .exception import TransitionNotAllowed

Handler = Callable[[m0HaObjState, m0HaObjState, Fid, Context], List[Action]]


class TransitStrategy:
    def __init__(self, workflow: ObjectWorkflow):
        self.transitions = self._create_transitions()
        self.workflow = workflow

    def do_transition(self, fid: Fid, old: m0HaObjState, new: m0HaObjState,
                      ctx: Context) -> List[Action]:
        if (old, new) not in self.transitions:
            raise TransitionNotAllowed()
        return self.transitions[(old, new)](old, new, fid, ctx)

    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        """
        Returns the mapping of the following kind:
            transition -> handler

        where transition is depicted by source and target states
              handler - function that generates side effects
        """
        raise RuntimeError('Not implemented')


class ProcessMove(TransitStrategy):
    def _nested_objects_needed(self, fid: Fid) -> bool:
        # Note: this is supposed to be the analogue of
        #       Motr._update_process_tree() method
        # TODO: find out whether broadcast_hax_only is needed as a parameter
        helper = self.workflow.helper
        return (not helper.is_proc_client(fid) and fid != helper.get_hax_fid())

    def _started(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                 ctx: Context) -> List[Action]:
        workflow = self.workflow
        helper = workflow.helper
        if helper.get_effective_status(fid) == ServiceHealth.OK:
            # We already know that the process is online, nothing to do.
            return []
        result: List[Action] = [
            SetObjectStatus(fid=fid, state=new),
            BroadcastState(fid=fid, state=ServiceHealth.OK)
        ]
        ctx = ctx.put('proc_fid', fid)
        if self._nested_objects_needed(fid):
            for nested in helper.get_services_under(fid):
                result.extend(workflow._get_actions(nested, new, ctx))
        return result

    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        # FIXME put the correct transition arrows according to the state
        # machine.
        #
        # FAILED = m0HaObjState.M0_NC_FAILED
        ONLINE = m0HaObjState.M0_NC_ONLINE
        # TRANSIENT = m0HaObjState.M0_NC_TRANSIENT
        UNKNOWN = m0HaObjState.M0_NC_UNKNOWN
        return {(UNKNOWN, ONLINE): self._started}


class ServiceMove(TransitStrategy):
    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        # FIXME put the correct transition arrows according to the state
        # machine.
        #
        # FAILED = m0HaObjState.M0_NC_FAILED
        ONLINE = m0HaObjState.M0_NC_ONLINE
        # TRANSIENT = m0HaObjState.M0_NC_TRANSIENT
        UNKNOWN = m0HaObjState.M0_NC_UNKNOWN
        return {(UNKNOWN, ONLINE): self._started}

    def _started(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                 ctx: Context) -> List[Action]:
        workflow = self.workflow
        helper = workflow.helper
        result: List[Action] = [
            BroadcastState(fid=fid, state=ServiceHealth.OK)
        ]
        for nested in helper.get_disks_by_service(fid):
            result.extend(workflow._get_actions(nested, new, ctx))
        return result


class DriveMove(TransitStrategy):
    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        # FIXME put the correct transition arrows according to the state
        # machine.
        #
        # FAILED = m0HaObjState.M0_NC_FAILED
        ONLINE = m0HaObjState.M0_NC_ONLINE
        TRANSIENT = m0HaObjState.M0_NC_TRANSIENT
        UNKNOWN = m0HaObjState.M0_NC_UNKNOWN
        return {
            (UNKNOWN, ONLINE): self._started,
            (ONLINE, TRANSIENT): self._stopped
        }

    def _started(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                 ctx: Context) -> List[Action]:
        result: List[Action] = [
            BroadcastState(fid=fid, state=ServiceHealth.OK),
            SetObjectStatus(fid=fid, state=new)
        ]
        return result

    def _stopped(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                 ctx: Context) -> List[Action]:
        workflow = self.workflow
        helper = workflow.helper
        proc_fid = ctx.get('proc_fid', Fid)
        is_mkfs = helper.is_mkfs(proc_fid)
        if is_mkfs:
            return []
        return [
            BroadcastState(fid=fid, state=ServiceHealth.FAILED),
            SetObjectStatus(fid=fid, state=new)
        ]
