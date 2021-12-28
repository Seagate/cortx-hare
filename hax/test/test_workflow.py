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

import json
from typing import List, Tuple, TypeVar

import inject
import pytest
from hax.motr.workflow import ConsulHelper, Executor, ObjectWorkflow
from hax.motr.workflow.action import BroadcastState
from hax.motr.workflow.common import Pager
from hax.queue.publish import BQPublisher
from hax.types import Fid, ObjT, m0HaObjState
from hax.util import ConsulUtil, KVAdapter, TxPutKV, dump_json, mk_fid


@pytest.fixture
def cns_helper(mocker):
    cns = mocker.create_autospec(ConsulUtil)
    helper = ConsulHelper(cns)
    return helper


class Collector(Executor):
    def __init__(self):
        self.output = None

    def execute(self, actions):
        self.output = actions


A = TypeVar('A')
B = TypeVar('B')


def _by_first(ret: List[Tuple[A, B]]):
    def f(x: A, *args) -> B:
        for fid, res in ret:
            if x == fid:
                return res
        raise RuntimeError(f'Unexpected parameter given: {x}')

    return f


def test_workflow_works(cns_helper: ConsulHelper, mocker):
    fid = mk_fid(ObjT.PROCESS, 12)
    mocker.patch.object(cns_helper,
                        'get_process_status_key_pair',
                        side_effect=_by_first([
                            (fid, ('a_key',
                                   json.dumps({
                                       'name': 'PROC!',
                                       'state': 'M0_NC_TRANSIENT'
                                   }))),
                        ]))

    ex = Collector()
    flow = ObjectWorkflow(executor=ex, helper=cns_helper)
    # import pudb.remote
    # pudb.remote.set_trace(term_size=(130, 50), port=9998)
    flow.transit(fid, m0HaObjState.M0_NC_DTM_RECOVERING)
    assert ex.output is not None
    assert len(ex.output.kv_ops) == 1
    kvop = ex.output.kv_ops[0]
    assert kvop.fid == fid
    assert kvop.key == 'a_key'
    assert json.loads(kvop.value) == {
        'name': 'PROC!',
        'state': 'M0_NC_DTM_RECOVERING'
    }
    assert kvop.state == m0HaObjState.M0_NC_DTM_RECOVERING
    assert len(ex.output.bcast_ops) > 0


def test_no_actions_if_state_not_changed(cns_helper: ConsulHelper, mocker):
    fid = mk_fid(ObjT.PROCESS, 12)
    mocker.patch.object(cns_helper,
                        'get_process_status_key_pair',
                        side_effect=_by_first([
                            (fid, ('a_key',
                                   json.dumps({
                                       'name': 'PROC!',
                                       'state': 'M0_NC_DTM_RECOVERING'
                                   }))),
                        ]))

    ex = Collector()
    flow = ObjectWorkflow(executor=ex, helper=cns_helper)
    # import pudb.remote
    # pudb.remote.set_trace(term_size=(130, 50), port=9998)
    flow.transit(fid, m0HaObjState.M0_NC_DTM_RECOVERING)
    assert ex.output is not None
    assert not ex.output


def test_process_started_updates_devices(cns_helper: ConsulHelper, mocker):
    fid = mk_fid(ObjT.PROCESS, 12)
    hax_fid = mk_fid(ObjT.PROCESS, 50)
    svc_fid = mk_fid(ObjT.SERVICE, 42)
    disks = [mk_fid(ObjT.SDEV, x) for x in [100, 101]]

    mocker.patch.object(cns_helper, 'is_proc_client', return_value=False)
    mocker.patch.object(cns_helper, 'get_hax_fid', return_value=hax_fid)
    mocker.patch.object(cns_helper,
                        'get_services_under',
                        return_value=[svc_fid])
    mocker.patch.object(cns_helper, 'get_disks_by_service', return_value=disks)
    mocker.patch.object(cns_helper,
                        'get_process_status_key_pair',
                        side_effect=_by_first([
                            (fid, ('a_key',
                                   json.dumps({
                                       'name': 'PROC!',
                                       'state': 'M0_NC_DTM_RECOVERING'
                                   }))),
                        ]))

    mocker.patch.object(cns_helper,
                        'get_kv',
                        side_effect=_by_first([
                            (f'a_key/services/{svc_fid}',
                             json.dumps({
                                 'name': 'PROC!',
                                 'state': 'M0_NC_TRANSIENT'
                             })),
                            (f'a_key/services/{svc_fid}/sdevs/{disks[0]}',
                             json.dumps({
                                 'path': '/dev/sda1',
                                 'state': 'M0_NC_TRANSIENT'
                             })),
                            (f'a_key/services/{svc_fid}/sdevs/{disks[1]}',
                             json.dumps({
                                 'path': '/dev/sda2',
                                 'state': 'M0_NC_TRANSIENT'
                             })),
                        ]))

    ex = Collector()
    flow = ObjectWorkflow(executor=ex, helper=cns_helper)
    flow.transit(fid, m0HaObjState.M0_NC_ONLINE)
    assert ex.output is not None
    assert len(ex.output.kv_ops) == 4
    fids = [x.fid for x in ex.output.kv_ops]
    assert fids == [fid, svc_fid, *disks]
    assert len(ex.output.bcast_ops) == 4


def test_pager_works():
    values = [1, 1, 2, 3, 5, 8, 13]
    p = Pager(values, 3)
    paginated = [x for x in p.get_next()]
    assert [[1, 1, 2], [3, 5, 8], [13]] == paginated
    assert [1, 1, 2, 3, 5, 8,
            13] == values, 'Pager mutates the given collection'


def test_pager_works_if_size_large():
    values = [1, 1, 2, 3, 5, 8]
    p = Pager(values, 20)
    paginated = [x for x in p.get_next()]
    assert [[1, 1, 2, 3, 5, 8]] == paginated


@pytest.fixture(autouse=True)
def inject_support(kv_adapter: KVAdapter):
    def configure(binder: inject.Binder):
        binder.bind(BQPublisher, BQPublisher(kv=kv_adapter))

    inject.clear_and_configure(configure)
    yield ''
    inject.clear()


@pytest.fixture
def kv_adapter(mocker):
    return mocker.create_autospec(KVAdapter)


def test_bq_broadcast_serializeable():
    bcast = BroadcastState(Fid(12, 13), m0HaObjState.M0_NC_DTM_RECOVERING)
    first = dump_json(bcast)
    assert first == '{"fid": "0xc:0xd", "state": 7}'


# flake8: noqa
def test_bq_can_publish_motr_bcast(mocker, kv_adapter):
    mocker.patch.object(kv_adapter,
                        'kv_get_raw',
                        return_value=(1, {
                            'Value': '12'
                        }))
    mocker.patch.object(kv_adapter, 'kv_put_in_transaction', return_value=True)
    bcast = BroadcastState(Fid(12, 13), m0HaObjState.M0_NC_DTM_RECOVERING)
    inject.instance(BQPublisher).publish('MOTR_BCAST', bcast)
    kv_adapter.kv_put_in_transaction.assert_called_once_with([
            TxPutKV(key='epoch', value='13', cas=1),
            TxPutKV(key='bq/13', value='{"message_type": "MOTR_BCAST", "payload": {"fid": "0xc:0xd", "state": 7}}',
                    cas=None)
            ])
