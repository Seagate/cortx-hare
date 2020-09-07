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

from dataclasses import dataclass
from typing import Any, List, Optional

from hax.motr import halink
from hax.types import Fid, HaNote, HAState, Uint128
from queue import Queue


class BaseMessage:
    pass


@dataclass
class Message(BaseMessage):
    s: str


@dataclass
class EntrypointRequest(BaseMessage):
    reply_context: Any
    req_id: Uint128
    remote_rpc_endpoint: str
    process_fid: Fid
    git_rev: str
    pid: int
    is_first_request: bool
    ha_link_instance: 'halink.HaLink'


@dataclass
class ProcessEvent(BaseMessage):
    evt: Any


@dataclass
class BroadcastHAStates(BaseMessage):
    states: List[HAState]
    reply_to: Optional[Queue]


@dataclass
class HaNvecGetEvent(BaseMessage):
    hax_msg: int
    nvec: List[HaNote]
    ha_link_instance: 'halink.HaLink'


@dataclass
class SnsOperation(BaseMessage):
    fid: Fid


class SnsRebalanceStart(SnsOperation):
    pass


class SnsRebalanceAbort(SnsOperation):
    pass


class SnsRebalancePause(SnsOperation):
    pass


class SnsRebalanceResume(SnsOperation):
    pass


class SnsRepairStart(SnsOperation):
    pass


class SnsRepairAbort(SnsOperation):
    pass


class SnsRepairPause(SnsOperation):
    pass


class SnsRepairResume(SnsOperation):
    pass


class SnsDiskAttach(SnsOperation):
    pass


class SnsDiskDetach(SnsOperation):
    pass


class Die(BaseMessage):
    pass
