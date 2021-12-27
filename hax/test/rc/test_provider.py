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

from typing import Dict, List, Tuple

import inject
import pytest
from hax.common import HaxGlobalState
from hax.queue.publish import BQPublisher, EQPublisher
from hax.rc import MessageProvider
from hax.util import KVAdapter


@pytest.fixture
def hax_state() -> HaxGlobalState:
    return HaxGlobalState()


@pytest.fixture(autouse=True)
def inject_support(hax_state: HaxGlobalState, kv_adapter: KVAdapter):
    def configure(binder: inject.Binder):
        binder.bind(HaxGlobalState, hax_state)
        binder.bind(EQPublisher, EQPublisher(kv=kv_adapter))
        binder.bind(BQPublisher, BQPublisher(kv=kv_adapter))

    inject.clear_and_configure(configure)
    yield ''
    inject.clear()


@pytest.fixture
def kv_adapter(mocker):
    return mocker.create_autospec(KVAdapter)


def new_kv(key: str, val: str):
    return {
        'Key': key,
        'CreateIndex': 1793,
        'ModifyIndex': 1793,
        'LockIndex': 0,
        'Flags': 0,
        'Value': val,
        'Session': ''
    }


def create_eq(values: List[Tuple[int, str]]) -> List[Dict[str, str]]:
    return [new_kv(f'eq/{k}', v) for k, v in values]


def eq(values: List[Tuple[int, str]]):
    def f(key, **kwargs):
        if key == 'eq/':
            return create_eq(values)
        raise RuntimeError(f'Unexpected key requested: {key}')

    return f


def test_provider_returns_none_if_eq_empty(mocker, kv_adapter: KVAdapter):
    mocker.patch.object(kv_adapter, 'kv_get', side_effect=eq([]))
    prov = MessageProvider(kv_adapter)
    ret = prov.get_next_message()
    assert ret is None


def test_provider_returns_message_if_it_exists(mocker, kv_adapter: KVAdapter):
    mocker.patch.object(kv_adapter, 'kv_get', side_effect=eq([(1, 'testme')]))
    prov = MessageProvider(kv_adapter)
    ret = prov.get_next_message()
    assert ret
    k, msg = ret
    assert k == 1
    assert msg['Value'] == 'testme'
    assert msg['Key'] == 'eq/1'


def test_provider_returns_msg_with_minimal_offset(mocker,
                                                  kv_adapter: KVAdapter):
    mocker.patch.object(kv_adapter,
                        'kv_get',
                        side_effect=eq([(14, 'testme14'), (13, 'testme13'),
                                        (11, 'testme11'), (12, 'testme12')]))
    prov = MessageProvider(kv_adapter)
    ret = prov.get_next_message()
    assert ret
    k, msg = ret
    assert k == 11
    assert msg['Value'] == 'testme11'
    assert msg['Key'] == 'eq/11'
