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

from typing import Any

import inject
import pytest
from hax.common import HaxGlobalState
from hax.exception import HAConsistencyException


@pytest.fixture
def hax_state() -> HaxGlobalState:
    return HaxGlobalState()


@pytest.fixture(autouse=True)
def inject_support(hax_state: HaxGlobalState):
    def configure(binder: inject.Binder):
        binder.bind(HaxGlobalState, hax_state)

    inject.clear_and_configure(configure)
    yield ''
    inject.clear()


def new_kv(key: str, val: Any):
    return {
        'Key': key,
        'CreateIndex': 1793,
        'ModifyIndex': 1793,
        'LockIndex': 0,
        'Flags': 0,
        'Value': val,
        'Session': ''
    }


def test_get_leader_node_raises_ha_consistency_when_no_key(
        mocker, consul_util):
    state: HaxGlobalState = inject.instance(HaxGlobalState)
    state.set_stopping()
    mocker.patch.object(consul_util.kv, 'kv_get', side_effect=[None])
    with pytest.raises(HAConsistencyException):
        consul_util.get_leader_node()


def test_get_leader_node_raises_ha_consistency_when_no_value(
        mocker, consul_util):
    state: HaxGlobalState = inject.instance(HaxGlobalState)
    state.set_stopping()
    mocker.patch.object(consul_util.kv,
                        'kv_get',
                        side_effect=[new_kv('leader', None)])
    with pytest.raises(HAConsistencyException):
        consul_util.get_leader_node()
