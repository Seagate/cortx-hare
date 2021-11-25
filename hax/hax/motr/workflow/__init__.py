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

import logging
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from hax.types import Fid, ObjT, ServiceHealth, m0HaObjState

from .action import Action
from .exception import TransitionForbidden, TransitionNotAllowed
from .transition import ProcessMove, TransitStrategy

LOG = logging.getLogger('hax')

__all__ = ['ObjectWorkflow']


class Executor:
    """ Action executor. The idea is that side effects of the transition are
    described as Action instances. The executor is free to bufferize the
    actions (e.g. group KV operations into Consul Transactions).

    The benefit of such an approach is that the list of actions can be
    accumulated even when transition includes some nested (recursive)
    transitions - even then the actions can be grouped for the sake of
    performance.
    """
    def execute(self, actions: List[Action]) -> None:
        # FIXME implement the real logic
        for i in actions:
            logging.info('Exec: %s', i)


C = TypeVar('C')


class Context:
    """ A type-safe intermittent whiteboard where some parent transitions may
    leave some meta information for nested transitions (e.g. whether the parent
    process is mkfs).
    """
    def __init__(self):
        self.data: Dict[str, Any] = {}

    def put(self, key: str, val: Any) -> 'Context':
        """ Puts the value to the storage and returns the updated instance.
            Note: old instance is not altered by this call.
        """

        # As the context is passed through recursive calls, we don't allow to
        # alter an existing instnace (reason: there is a risk of dirty write
        # somwhere deep in recursive that can affect other transitions in the
        # sequence).
        new_dict = dict(self.data)
        new_dict[key] = val
        ctx = Context()
        ctx.data = new_dict
        return ctx

    def get(self, key: str, as_type: Type[C]) -> C:
        """ Return the value by the key and verify that the value is of the
        given type; if the type doesn't match, RuntimeError is thrown.
        """
        value = self.data.get(key)
        if not isinstance(value, as_type):
            raise RuntimeError(f'Business logic error: {as_type} type '
                               f'expected but {value} is given')

        return value


class ConsulHelper:
    # This is a kind of a bridge between the ObjectWorfklow and ConsulUtil.

    def get_current_state(self, fid: Fid) -> m0HaObjState:
        """ Reads the latest known state of the object from Consul KV.
        """
        raise RuntimeError('Not implemented')

    def get_effective_status(self, fid: Fid) -> ServiceHealth:
        """ Evaluates the actual effective health status of the given process.
        """
        raise RuntimeError('Not implemented')

    def is_proc_client(self, fid: Fid) -> bool:
        raise RuntimeError('Not implemented')

    def get_hax_fid(self) -> Fid:
        raise RuntimeError('Not implemented')

    def get_services_under(self, fid: Fid) -> List[Fid]:
        raise RuntimeError('Not implemented')

    def get_disks_by_service(self, fid: Fid) -> List[Fid]:
        raise RuntimeError('Not implemented')

    def is_mkfs(self, proc_fid: Fid) -> List[Fid]:
        raise RuntimeError('Not implemented')

    def get_owning_process(self, service_fid: Fid) -> Fid:
        raise RuntimeError('Not implemented')


class ObjectWorkflow:
    """ Central class for changing the object state through the DTM state
    machine."""
    def __init__(self,
                 executor: Optional[Executor] = None,
                 helper: Optional[ConsulHelper] = None):
        self.movers: Dict[ObjT, TransitStrategy] = {
            ObjT.PROCESS: ProcessMove(self)
        }
        self.executor = executor or Executor()
        self.helper = helper or ConsulHelper()

    def transit(self, fid: Fid, new: m0HaObjState) -> None:
        """ Perform the state transition of the given object.

            - fid - Fid that identifies the object.
            - new - Target state of the transition.
        """
        actions = self._get_actions(fid, new, Context())
        self.executor.execute(actions)

    def transit_all(self, states_and_fids: List[Tuple[Fid,
                                                      m0HaObjState]]) -> None:
        """ Perform the state transition of the given objects.

            Each list element describes one object state change of the
            following kind:
            - fid - Fid that identifies the object.
            - new - Target state of the transition.
        """
        actions: List[Action] = []
        for fid, state in states_and_fids:
            actions.extend(self._get_actions(fid, state, Context()))
        self.executor.execute(actions)

    def _get_type(self, fid: Fid) -> ObjT:
        try:
            return fid.get_type()
        except KeyError:
            raise TransitionForbidden(f'Unsupported fid type given: {fid}')

    def _get_actions(self, fid, new: m0HaObjState,
                     ctx: Context) -> List[Action]:
        f_type = fid.get_type()
        old = self.helper.get_current_state(fid)
        if f_type not in self.movers:
            # TODO it may happen that the problem is that the requested
            # transition is obsolete (example: the object is ALREADY in new
            # state). Do we want to ignore that transition without an
            # exception?
            raise TransitionNotAllowed()
        actions = self.movers[f_type].do_transition(fid, old, new, ctx)
        return actions
