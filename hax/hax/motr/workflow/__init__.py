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
from typing import List, Tuple

from hax.consul.cache import create_kv_cache
from hax.types import Fid, HaNoteStruct, m0HaObjState
from hax.util import TxPutKV
from hax.queue.publish import BQPublisher

from .action import ActionHolder, ActionProvider, BroadcastState, SetKV
from .common import ConsulHelper, Context, Pager

LOG = logging.getLogger('hax')

MAX_CONSUL_TX_LEN = 64
MAX_MOTR_BCAST_LEN = 1024


class Executor:
    """ Action executor. The idea is that side effects of the transition are
    described as Action instances. The executor is free to bufferize the
    actions (e.g. group KV operations into Consul Transactions).

    The benefit of such an approach is that the list of actions can be
    accumulated even when transition includes some nested (recursive)
    transitions - even then the actions can be grouped for the sake of
    performance.
    """
    def __init__(self, cns: ConsulHelper, pub: BQPublisher):
        self.cns = cns
        self.pub = pub

    def execute(self, actions: ActionHolder) -> None:
        self._run_kv(actions.kv_ops)
        self._run_bcast(actions.bcast_ops)

    def _run_kv(self, kvs: List[SetKV]):
        pager = Pager(kvs, MAX_CONSUL_TX_LEN)
        for page in pager.get_next():
            tx_data = [
                TxPutKV(key=x.key, value=str(x.state), cas=None) for x in page
            ]
            self.cns.put_kv(tx_data)

    def _run_bcast(self, actions: List[BroadcastState]):
        # to_send = [
        #     HaNoteStruct(no_id=item.fid.to_c(),
        #                  no_state=item.state.to_ha_note_status())
        #     for item in actions
        # ]
        # # TODO: do we need this broadcast_hax_only?
        # self.motr.ha_broadcast(to_send, broadcast_hax_only=False)
        self.pub.publish('MOTR_BCAST', actions)


class ObjectWorkflow:
    """ Central class for changing the object state through the DTM state
    machine."""
    def __init__(self, executor: Executor, helper: ConsulHelper):
        self.executor = executor
        self.provider = ActionProvider(helper)

    def transit(self, fid: Fid, new: m0HaObjState) -> None:
        """ Perform the state transition of the given object.

            - fid - Fid that identifies the object.
            - new - Target state of the transition.
        """
        actions = self.provider.get_actions(fid, new, self._create_ctx())
        self.executor.execute(actions)

    def transit_all(self, states_and_fids: List[Tuple[Fid,
                                                      m0HaObjState]]) -> None:
        """ Perform the state transition of the given objects.

            Each list element describes one object state change of the
            following kind:
            - fid - Fid that identifies the object.
            - new - Target state of the transition.
        """
        actions = ActionHolder()
        p = self.provider
        for fid, state in states_and_fids:
            actions.extend(p.get_actions(fid, state, self._create_ctx()))
        self.executor.execute(actions)

    def _create_ctx(self) -> Context:
        ctx = Context()
        ctx.put('kv_cache', create_kv_cache())
        return ctx
