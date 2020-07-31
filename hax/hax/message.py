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

from typing import Any, List

from hax import halink
from hax.types import Fid, HaNote, HAState, Uint128


class BaseMessage:
    pass


class Message(BaseMessage):
    def __init__(self, s):
        self.s = s


class EntrypointRequest(BaseMessage):
    def __init__(self, reply_context: Any, req_id: Uint128,
                 remote_rpc_endpoint: str, process_fid: Fid, git_rev: str,
                 pid: int, is_first_request: bool,
                 ha_link_instance: 'halink.HaLink'):
        self.reply_context = reply_context
        self.req_id = req_id
        self.remote_rpc_endpoint = remote_rpc_endpoint
        self.process_fid = process_fid
        self.git_rev = git_rev
        self.pid = pid
        self.is_first_request = is_first_request
        self.ha_link_instance = ha_link_instance


class ProcessEvent(BaseMessage):
    def __init__(self, evt):
        self.evt = evt


class BroadcastHAStates(BaseMessage):
    def __init__(self, states: List[HAState]):
        self.states = states


class HaNvecGetEvent(BaseMessage):
    def __init__(self, hax_msg: int, nvec: List[HaNote],
                 ha_link_instance: 'halink.HaLink'):
        self.hax_msg = hax_msg
        self.nvec = nvec
        self.ha_link_instance = ha_link_instance


class Die(BaseMessage):
    pass
