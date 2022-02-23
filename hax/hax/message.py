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

import queue as q
from dataclasses import dataclass, field, fields
from queue import Queue
from typing import Any, List, Optional

from hax.types import ConfHaProcess, Fid, HaNote, HAState, StobId, Uint128


@dataclass(unsafe_hash=True)
class BaseMessage:
    # The group id used internally by WorkPlanner
    group: Optional[int] = field(default=None, init=False)


@dataclass(unsafe_hash=True)
class AnyEntrypointRequest(BaseMessage):
    reply_context: Any
    req_id: Uint128
    remote_rpc_endpoint: str
    process_fid: Fid
    git_rev: str
    pid: int
    is_first_request: bool


@dataclass(unsafe_hash=True)
class EntrypointRequest(AnyEntrypointRequest):
    pass


@dataclass
class FirstEntrypointRequest(AnyEntrypointRequest):
    pass


@dataclass
class ProcessEvent(BaseMessage):
    evt: ConfHaProcess


@dataclass
class BroadcastHAStates(BaseMessage):
    states: List[HAState]
    reply_to: Optional[Queue]


@dataclass
class HaNvecGetEvent(BaseMessage):
    hax_msg: int
    nvec: List[HaNote]

    def __repr__(self):
        return f'HaNvecGetEvent(<{len(self.nvec)} items>)'


@dataclass
class HaNvecSetEvent(BaseMessage):
    hax_msg: int
    nvec: List[HaNote]

    def __repr__(self):
        return f'HaNvecSetEvent(<{len(self.nvec)} items>)'


@dataclass
class SnsOperation(BaseMessage):
    fid: Fid


class SnsRebalanceStart(SnsOperation):
    pass


class SnsRebalanceStop(SnsOperation):
    pass


class SnsRebalancePause(SnsOperation):
    pass


class SnsRebalanceResume(SnsOperation):
    pass


class SnsRepairStart(SnsOperation):
    pass


class SnsRepairStop(SnsOperation):
    pass


class SnsRepairPause(SnsOperation):
    pass


class SnsRepairResume(SnsOperation):
    pass


class SnsDiskAttach(SnsOperation):
    pass


class SnsDiskDetach(SnsOperation):
    pass


@dataclass
class SnsRepairStatus(SnsOperation):
    fid: Fid
    reply_to: q.Queue


@dataclass
class SnsRebalanceStatus(SnsOperation):
    fid: Fid
    reply_to: q.Queue


@dataclass
class StobIoqError(BaseMessage):
    fid: Fid
    conf_sdev: Fid
    stob_id: StobId
    fd: int
    opcode: int
    rc: int
    offset: int
    size: int
    bshift: int

    def for_json(self):
        parts = {}

        def as_str(a):
            return str(a)

        def as_repr(a):
            return repr(a)

        def as_is(a):
            return a

        for fld in fields(self):
            f_type = fld.type
            f_name = fld.name
            if f_name == 'group':
                # group is a thing used by WorkPlanner for task scheduling
                # logic. We don't need to expose it
                continue
            val = getattr(self, f_name)
            to_str = as_str
            if f_type is Fid:
                to_str = as_repr
            elif f_type is StobId:
                to_str = as_is
            elif f_type is int or f_type is None:
                to_str = as_is
            parts[fld.name] = to_str(val)

        return parts


class Die(BaseMessage):
    pass
