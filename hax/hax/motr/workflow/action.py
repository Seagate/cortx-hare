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
import json
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from hax.types import Fid, ObjT, m0HaObjState

from .common import ConsulHelper, Context
from .exception import TransitionForbidden, TransitionNotAllowed


@dataclass
class Action:
    pass


@dataclass
class BroadcastState(Action):
    fid: Fid
    state: m0HaObjState


@dataclass
class SetKV(Action):
    key: str
    value: str
    fid: Fid
    state: m0HaObjState


@dataclass
class IncrementEpoch(Action):
    # TBD do we need to know the object fid who caused the epoch to increment?
    pass


class ActionHolder:
    """ Container for a list of actions. For the sake of performance, this
    container separates KV operations from broadcast actions (so each group can
    be bufferized afterwards)
    """
    def __init__(self, *args: Action):
        self.kv_ops: List[SetKV] = []
        self.bcast_ops: List[BroadcastState] = []
        self.other_ops: List[Action] = []
        self.add(args)

    def add(self, ops: Iterable[Action]):
        for i in ops:
            if isinstance(i, SetKV):
                self.kv_ops.append(i)
            elif isinstance(i, BroadcastState):
                self.bcast_ops.append(i)
            else:
                self.other_ops.append(i)

    def get_all(self) -> List[Action]:
        return [*self.kv_ops, *self.bcast_ops, *self.other_ops]

    def get_kv_actions(self) -> List[SetKV]:
        return self.kv_ops

    def get_bcast_actions(self) -> List[BroadcastState]:
        return self.bcast_ops

    def get_other_actions(self) -> List[Action]:
        return self.other_ops

    def extend(self, a_holder: 'ActionHolder'):
        self.kv_ops.extend(a_holder.kv_ops)
        self.bcast_ops.extend(a_holder.bcast_ops)
        self.other_ops.extend(a_holder.other_ops)

    def __bool__(self) -> bool:
        # This function allows checking the holder for emptiness as if it is
        # a boolean expression - "if not holder:"
        return bool(self.kv_ops or self.bcast_ops or self.other_ops)


Handler = Callable[[m0HaObjState, m0HaObjState, Fid, Context], ActionHolder]


class TransitStrategy:
    def __init__(self, provider: 'ActionProvider'):
        self.transitions = self._create_transitions()
        self.provider = provider

    def do_transition(self, fid: Fid, new: m0HaObjState,
                      ctx: Context) -> ActionHolder:
        _, value = self._get_kv_key(fid, ctx)
        if not value:
            # impossible situation: the corresponding {name, state}
            # JSONs are generated in cfgen.
            raise RuntimeError('Business logic error: process status '
                               f'[fid={fid}] has no value in KV.')

        old = self._parse_state_from_kv_value(value)

        if old == new:
            return ActionHolder()

        if (old, new) not in self.transitions:
            raise TransitionNotAllowed()
        actions = self.transitions[(old, new)](old, new, fid, ctx)
        return actions

    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        """
        Returns the mapping of the following kind:
            transition -> handler

        where transition is depicted by source and target states
              handler - function that generates side effects
        """
        raise RuntimeError('Not implemented')

    def _create_kv(self, fid: Fid, state: m0HaObjState, ctx: Context) -> SetKV:
        key, old_val = self._get_kv_key(fid, ctx)
        return SetKV(fid=fid,
                     state=state,
                     key=key,
                     value=self._get_new_value(fid, state, old_val))

    def _parse_state_from_kv_value(self, value: str) -> m0HaObjState:
        raise RuntimeError('Not implemented')

    def _get_kv_key(self, fid: Fid, ctx: Context) -> Tuple[str, Optional[str]]:
        raise RuntimeError('Not implemented')

    def _get_new_value(self, fid: Fid, state: m0HaObjState,
                       old_value: Optional[str]) -> str:
        raise RuntimeError('Not implemented')

    def _mark_and_broadcast(self, old: m0HaObjState, new: m0HaObjState,
                            fid: Fid, ctx: Context) -> ActionHolder:
        actions, _ = self._mark_and_broadcast_ex(old, new, fid, ctx)
        return actions

    def _mark_and_broadcast_ex(self, old: m0HaObjState, new: m0HaObjState,
                               fid: Fid,
                               ctx: Context) -> Tuple[ActionHolder, Context]:
        raise RuntimeError('Not implemented')


class ProcessMove(TransitStrategy):
    def _mark_and_broadcast_ex(self, old: m0HaObjState, new: m0HaObjState,
                               fid: Fid,
                               ctx: Context) -> Tuple[ActionHolder, Context]:
        kv_action = self._create_kv(fid, new, ctx)
        result = ActionHolder(BroadcastState(fid=fid, state=new), kv_action)
        ctx = ctx.put('proc_kv_key', kv_action.key)
        return (result, ctx)

    def _nested_objects_needed(self, fid: Fid) -> bool:
        # Note: this is supposed to be the analogue of
        #       Motr._update_process_tree() method
        # TODO: find out whether broadcast_hax_only is needed as a parameter
        helper = self.provider.helper
        return (not helper.is_proc_client(fid) and fid != helper.get_hax_fid())

    def _get_kv_key(self, fid: Fid, ctx: Context) -> Tuple[str, str]:
        helper = self.provider.helper
        return helper.get_process_status_key_pair(fid, ctx)

    def _parse_state_from_kv_value(self, value: str) -> m0HaObjState:
        parsed = json.loads(value)
        return m0HaObjState.parse(parsed['state'])

    def _get_new_value(self, fid: Fid, state: m0HaObjState,
                       old_value: Optional[str]) -> str:
        if not old_value:
            # impossible situation: the corresponding {name, state}
            # JSONs are generated in cfgen.
            raise RuntimeError('Business logic error: process status '
                               f'[fid={fid}] has no value in KV.')

        value = json.loads(old_value)
        value['state'] = repr(state)
        return json.dumps(value)

    def _recovered(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                   ctx: Context) -> ActionHolder:
        result, ctx = self._mark_and_broadcast_ex(old, new, fid, ctx)
        if not result:
            return result
        provider = self.provider
        helper = provider.helper
        ctx = ctx.put('proc_fid', fid)
        if self._nested_objects_needed(fid):
            for nested in helper.get_services_under(fid):
                result.extend(provider.get_actions(nested, new, ctx))
        return result

    def _transient(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                   ctx: Context) -> ActionHolder:
        result, ctx = self._mark_and_broadcast_ex(old, new, fid, ctx)
        if not result:
            return result
        provider = self.provider
        helper = provider.helper
        ctx = ctx.put('proc_fid', fid).put('is_mkfs', helper.is_mkfs(fid))
        if self._nested_objects_needed(fid):
            for nested in helper.get_services_under(fid):
                result.extend(provider.get_actions(nested, new, ctx))
        return result

    def _failed(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                ctx: Context) -> ActionHolder:
        result, ctx = self._mark_and_broadcast_ex(old, new, fid, ctx)

        provider = self.provider
        helper = provider.helper
        ctx = ctx.put('proc_fid', fid).put('is_mkfs', helper.is_mkfs(fid))
        if self._nested_objects_needed(fid):
            for nested in helper.get_services_under(fid):
                result.extend(provider.get_actions(nested, new, ctx))
        return result

    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        FAILED = m0HaObjState.M0_NC_FAILED
        ONLINE = m0HaObjState.M0_NC_ONLINE
        TRANSIENT = m0HaObjState.M0_NC_TRANSIENT
        RECOVERING = m0HaObjState.M0_NC_DTM_RECOVERING
        return {
            (TRANSIENT, RECOVERING): self._mark_and_broadcast,
            (TRANSIENT, FAILED): self._failed,
            (FAILED, RECOVERING): self._mark_and_broadcast,
            (RECOVERING, ONLINE): self._recovered,
            (RECOVERING, TRANSIENT): self._transient,
            (ONLINE, TRANSIENT): self._transient
        }


class ServiceMove(TransitStrategy):
    def _get_kv_key(self, fid: Fid, ctx: Context) -> Tuple[str, str]:
        helper = self.provider.helper
        # we assume that Service status change happens only as a part of a
        # Process state transition (that's why the context has the process KV
        # key already)
        proc_key = ctx.get('proc_kv_key', str)
        key = f'{proc_key}/services/{fid}'
        value = helper.get_kv(key, ctx)

        return (key, value)

    def _parse_state_from_kv_value(self, value: str) -> m0HaObjState:
        parsed = json.loads(value)
        return m0HaObjState.parse(parsed['state'])

    def _get_new_value(self, fid: Fid, state: m0HaObjState,
                       old_value: Optional[str]) -> str:
        if not old_value:
            # impossible situation: the corresponding {name, state}
            # JSONs are generated in cfgen.
            raise RuntimeError('Business logic error: service status '
                               f'[fid={fid}] has no value in KV.')

        value = json.loads(old_value)
        value['state'] = repr(state)
        return json.dumps(value)

    def _mark_and_broadcast_ex(self, old: m0HaObjState, new: m0HaObjState,
                               fid: Fid,
                               ctx: Context) -> Tuple[ActionHolder, Context]:
        kv_action = self._create_kv(fid, new, ctx)
        result = ActionHolder(BroadcastState(fid=fid, state=new), kv_action)
        ctx = ctx.put('service_kv_key', kv_action.key)
        return (result, ctx)

    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        # FIXME put the correct transition arrows according to the state
        # machine.
        #
        FAILED = m0HaObjState.M0_NC_FAILED
        ONLINE = m0HaObjState.M0_NC_ONLINE
        TRANSIENT = m0HaObjState.M0_NC_TRANSIENT
        return {
            (TRANSIENT, ONLINE): self._mark_with_drives,
            (ONLINE, TRANSIENT): self._mark_with_drives,
            (TRANSIENT, FAILED): self._mark_and_broadcast,
            (FAILED, ONLINE): self._mark_with_drives
        }

    def _mark_with_drives(self, old: m0HaObjState, new: m0HaObjState, fid: Fid,
                          ctx: Context) -> ActionHolder:
        provider = self.provider
        helper = provider.helper
        result, ctx = self._mark_and_broadcast_ex(old, new, fid, ctx)
        if not result:
            return result
        for nested in helper.get_disks_by_service(fid):
            result.extend(provider.get_actions(nested, new, ctx))
        return result


class HwMove(TransitStrategy):
    """ Transition strategy for Node, Storage device, Enclosure and Controller.
    """
    def _get_new_value(self, fid: Fid, state: m0HaObjState,
                       old_value: Optional[str]) -> str:
        if not old_value:
            # impossible situation: the corresponding {name, state}
            # JSONs are generated in cfgen.
            raise RuntimeError('Business logic error: service status '
                               f'[fid={fid}] has no value in KV.')

        value = json.loads(old_value)
        value['state'] = repr(state)
        return json.dumps(value)

    def _parse_state_from_kv_value(self, value: str) -> m0HaObjState:
        parsed = json.loads(value)
        return m0HaObjState.parse(parsed['state'])

    def _create_transitions(
            self) -> Dict[Tuple[m0HaObjState, m0HaObjState], Handler]:
        FAILED = m0HaObjState.M0_NC_FAILED
        ONLINE = m0HaObjState.M0_NC_ONLINE
        TRANSIENT = m0HaObjState.M0_NC_TRANSIENT
        return {
            (TRANSIENT, ONLINE): self._mark_and_broadcast,
            (ONLINE, TRANSIENT): self._mark_and_broadcast,
            (TRANSIENT, FAILED): self._mark_and_broadcast,
            (FAILED, ONLINE): self._mark_and_broadcast
        }

    def _mark_and_broadcast(self, old: m0HaObjState, new: m0HaObjState,
                            fid: Fid, ctx: Context) -> ActionHolder:
        kv_action = self._create_kv(fid, new, ctx)
        result = ActionHolder(BroadcastState(fid=fid, state=new), kv_action)
        return result


class SdevMove(HwMove):
    def _get_kv_key(self, fid: Fid, ctx: Context) -> Tuple[str, str]:
        helper = self.provider.helper
        # we assume that Sdev status change happens only as a part of a
        # Process state transition (that's why the context has the process KV
        # key already)
        svc_key = ctx.get('service_kv_key', str)
        key = f'{svc_key}/sdevs/{fid}'
        value = helper.get_kv(key, ctx)

        return (key, value)


class EnclMove(HwMove):
    def _get_kv_key(self, fid: Fid, ctx: Context) -> Tuple[str, str]:
        raise RuntimeError('Not implemented')


class NodeMove(HwMove):
    def _get_kv_key(self, fid: Fid, ctx: Context) -> Tuple[str, str]:
        raise RuntimeError('Not implemented')


class ActionProvider:
    def __init__(self, helper: ConsulHelper):
        self.helper = helper
        self.movers: Dict[ObjT, TransitStrategy] = {
            ObjT.PROCESS: ProcessMove(self),
            ObjT.SERVICE: ServiceMove(self),
            ObjT.SDEV: SdevMove(self),
        }

    def get_actions(self, fid, new: m0HaObjState,
                    ctx: Context) -> ActionHolder:
        f_type = self._get_type(fid)
        actions = self.movers[f_type].do_transition(fid, new, ctx)
        return actions

    def _get_type(self, fid: Fid) -> ObjT:
        try:
            return fid.get_type()
        except KeyError:
            raise TransitionForbidden(f'Unsupported fid type given: {fid}')
