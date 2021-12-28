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
from typing import Any, Dict, List, Tuple, Union

import inject
import simplejson
from hax.consul.cache import create_kv_cache
from hax.motr.workflow import ObjectWorkflow
from hax.motr.workflow.common import ConsulHelper, Context
from hax.queue.publish import BQPublisher
from hax.types import Fid, m0HaObjState
from hax.util import create_process_fid

LOG = logging.getLogger('hax')

P = Union[Dict[str, Any], List[Any]]


class EqMessageHandler:
    def handle(self, msg_type: str, payload: P) -> None:
        raise RuntimeError('Not implemented')


class NullHandler(EqMessageHandler):
    def handle(self, msg_type: str, payload: P) -> None:
        LOG.debug('Message [type=%s] is unsupported. Skipped', msg_type)


class StobIoqErrorHandler(EqMessageHandler):
    def handle(self, msg_type: str, payload: P) -> None:
        pub = inject.instance(BQPublisher)
        pub.publish(msg_type, payload)


class ProcHealthUpdateHandler(EqMessageHandler):
    def __init__(self):
        self.helper = inject.instance(ConsulHelper)

    def handle(self, msg_type: str, payload: P) -> None:
        workflow = inject.instance(ObjectWorkflow)
        if not isinstance(payload, list):
            raise RuntimeError('Business logic error: list is expected but ' +
                               type(payload).__name__ + 'is given')

        workflow.transit_all(self._to_states(payload))

    def _to_states(
            self, data: List[Dict[str,
                                  Any]]) -> List[Tuple[Fid, m0HaObjState]]:
        if not data:
            return []
        helper = self.helper

        def is_alive(checks: List[Dict[str, Any]]) -> bool:
            return all(x.get('Status') == 'passing' for x in checks)

        def parse_old_state(val: str) -> m0HaObjState:
            value = simplejson.loads(val)
            return m0HaObjState.parse(value['state'])

        ctx = Context().put('kv_cache', create_kv_cache())

        result: List[Tuple[Fid, m0HaObjState]] = []
        for item in data:
            ok = is_alive(item['Checks'])
            fid = create_process_fid(int(item['Service']['ID']))
            _, kv_val = helper.get_process_status_key_pair(fid, ctx)
            m0state = parse_old_state(kv_val)

            # Let's check whether health update brought by Consul does change
            # the currently known status of the process.
            if ok and m0state in (m0HaObjState.M0_NC_FAILED,
                                  m0HaObjState.M0_NC_TRANSIENT):
                result.append((fid, m0HaObjState.M0_NC_DTM_RECOVERING))
            elif not ok and m0state in (m0HaObjState.M0_NC_DTM_RECOVERING,
                                        m0HaObjState.M0_NC_ONLINE):
                result.append((fid, m0HaObjState.M0_NC_TRANSIENT))

        return result
