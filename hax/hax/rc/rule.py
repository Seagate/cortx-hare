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
from typing import Any, Dict

import inject
from hax.queue.publish import BQPublisher

LOG = logging.getLogger('hax')

P = Dict[str, Any]


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
    def handle(self, msg_type: str, payload: P) -> None:
        raise RuntimeError('Implement me')
