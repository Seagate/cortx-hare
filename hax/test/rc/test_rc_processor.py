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
from base64 import b64encode
from typing import Dict, List, Tuple, cast
from unittest.mock import Mock

import inject
import pytest
import simplejson
from hax.common import HaxGlobalState
from hax.message import StobId, StobIoqError
from hax.queue.publish import BQPublisher, EQPublisher
from hax.rc import RCProcessorThread, Synchronizer
from hax.types import Fid
from hax.util import KVAdapter, dump_json


@pytest.fixture
def hax_state() -> HaxGlobalState:
    return HaxGlobalState()


@pytest.fixture
def bq_pub(mocker) -> BQPublisher:
    return mocker.create_autospec(BQPublisher)


@pytest.fixture(autouse=True)
def inject_support(hax_state: HaxGlobalState, kv_adapter: KVAdapter,
                   bq_pub: BQPublisher):
    def configure(binder: inject.Binder):
        binder.bind(HaxGlobalState, hax_state)
        binder.bind(EQPublisher, EQPublisher(kv=kv_adapter))
        binder.bind(BQPublisher, bq_pub)

    inject.clear_and_configure(configure)
    yield ''
    inject.clear()


@pytest.fixture
def synchronizer(mocker):
    return mocker.create_autospec(Synchronizer)


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


def test_sleeps_and_returns_if_no_messages(mocker, kv_adapter: KVAdapter,
                                           synchronizer: Synchronizer):
    mocker.patch.object(kv_adapter, 'kv_get', side_effect=eq([]))
    processor = RCProcessorThread(synchronizer, kv_adapter)
    processor._process_next()
    m_synch = cast(Mock, synchronizer)
    assert m_synch.sleep.called


def base64(s: str) -> str:
    b64: bytes = b64encode(s.encode())
    return b64.decode()


def test_ioq_stob_supported(mocker, kv_adapter: KVAdapter,
                            synchronizer: Synchronizer, bq_pub):
    stob = StobId(Fid(12, 13), Fid(14, 15))
    msg = StobIoqError(fid=Fid(5, 6),
                       conf_sdev=Fid(0x103, 0x204),
                       stob_id=stob,
                       fd=42,
                       opcode=4,
                       rc=2,
                       offset=0xBF,
                       size=100,
                       bshift=4)

    # Here we make sure that rea StobIoqError can be used as the payload
    # for STOB_IOQ_ERROR bq message.
    stob_payload = dump_json(msg)
    parsed_stob = simplejson.loads(stob_payload)

    event_payload = {'message_type': 'STOB_IOQ_ERROR', 'payload': parsed_stob}
    mocker.patch.object(kv_adapter,
                        'kv_get',
                        side_effect=eq([
                            (12, base64(simplejson.dumps(event_payload)))
                        ]))
    processor = RCProcessorThread(synchronizer, kv_adapter)
    processor._process_next()
    m_synch = cast(Mock, synchronizer)
    assert not m_synch.sleep.called
    m_bq = cast(Mock, bq_pub)
    m_bq.publish.assert_called_with('STOB_IOQ_ERROR', parsed_stob)
