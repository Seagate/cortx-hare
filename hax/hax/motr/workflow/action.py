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
from dataclasses import dataclass

from hax.types import Fid, ServiceHealth, m0HaObjState


@dataclass
class Action:
    pass


@dataclass
class BroadcastState(Action):
    fid: Fid
    state: ServiceHealth


@dataclass
class KV(Action):
    pass


@dataclass
class SetObjectStatus(KV):
    fid: Fid
    state: m0HaObjState


@dataclass
class IncrementEpoch(KV):
    # TBD do we need to know the object fid who caused the epoch to increment?
    pass
