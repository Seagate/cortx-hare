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
import pytest
from hax.types import HaNoteStruct, ServiceHealth

h = HaNoteStruct
s = ServiceHealth


@pytest.mark.parametrize('ha_note,health', [(h.M0_NC_ONLINE, s.OK),
                                            (h.M0_NC_FAILED, s.FAILED),
                                            (h.M0_NC_TRANSIENT, s.OFFLINE),
                                            (h.M0_NC_UNKNOWN, s.UNKNOWN)])
def test_service_health_to_ha_note(ha_note: int, health: ServiceHealth):
    assert ha_note == health.to_ha_note_status()


@pytest.mark.parametrize('ha_note,health', [(h.M0_NC_ONLINE, s.OK),
                                            (h.M0_NC_FAILED, s.FAILED),
                                            (h.M0_NC_TRANSIENT, s.OFFLINE),
                                            (h.M0_NC_UNKNOWN, s.UNKNOWN),
                                            (h.M0_NC_REPAIRED, s.UNKNOWN)])
def test_ha_note_to_service_health_works(ha_note: int, health: ServiceHealth):
    assert ServiceHealth.from_ha_note_state(ha_note) == health
