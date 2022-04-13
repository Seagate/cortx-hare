# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
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

import enum


# Following are the replicas of ha constants(EVENT_MANAGER_KEYS,
# FAULT_TOLERANCE_KEYS, HEALTH_EVENT_SOURCES, NOT_DEFINED) and added as
# temporary fix because HA rpm is not available in data and server pod.
# These should be removed once proper fix is available
class EVENT_MANAGER_KEYS(enum.Enum):
    MESSAGE_TYPE_VALUE = "ha_event_hare"


class FAULT_TOLERANCE_KEYS(enum.Enum):
    HARE_HA_MESSAGE_TYPE = 'cortx_health_events'


class HEALTH_EVENT_SOURCES(enum.Enum):
    HA = 'ha'
    HARE = 'hare'
    MONITOR = 'monitor'


NOT_DEFINED = 'NOT_DEFINED'
