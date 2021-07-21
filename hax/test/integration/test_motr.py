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

import ctypes

import pytest
from hax.handler import ConsumerThread
from hax.message import BaseMessage, Die, FirstEntrypointRequest
from hax.motr import Motr, WorkPlanner
from hax.motr.delivery import DeliveryHerald
from hax.motr.ffi import HaxFFI
from hax.types import Fid, HaNoteStruct, Profile, Uint128
from hax.util import create_process_fid, create_profile_fid

from .testutils import (AssertionPlan, FakeFFI, Invocation, TraceMatcher,
                        tr_and, tr_method)


@pytest.fixture
def herald(mocker):
    herald = DeliveryHerald()
    mocker.patch.object(herald, 'wait_for_all')
    return herald


@pytest.fixture
def planner(mocker) -> WorkPlanner:
    planner = WorkPlanner()
    mocker.patch.object(planner, 'add_command', side_effect=RuntimeError())
    return planner


def ha_note_failed() -> TraceMatcher:
    '''
    Returns true if the second argument is a pointer to HaNoteStruct and that
    structure brings M0_NC_FAILED state.

    It makes sense to use this matcher together with
    `tr_method('ha_broadcast')`
    '''
    def fn(trace: Invocation) -> bool:
        if len(trace.args) < 2:
            return False
        note = trace.args[1]
        if not isinstance(note, ctypes.Array):
            return False

        # It seems like the ctype pointer always looks like an array from
        # outside. We have to cast it explicitly to (HaNoteStruct *) to
        # dereference it.
        ptr = ctypes.cast(note, ctypes.POINTER(HaNoteStruct))

        state: int = ptr.contents.no_state
        return state == HaNoteStruct.M0_NC_FAILED

    return fn


@pytest.fixture
def ffi() -> HaxFFI:
    return FakeFFI()


@pytest.fixture
def motr(mocker, ffi, planner, herald, consul_util) -> Motr:
    motr = Motr(ffi, planner, herald, consul_util)
    return motr


@pytest.fixture
def consumer(planner, motr, herald, consul_util):
    return ConsumerThread(planner, motr, herald, consul_util, 0)


def run_in_consumer(mocker, msg: BaseMessage, planner: WorkPlanner,
                    consumer: ConsumerThread, motr: Motr) -> None:
    mocker.patch.object(planner, 'get_next_command', side_effect=[msg, Die()])
    profile = Profile(fid=create_profile_fid(22),
                      name='the_pool',
                      pool_names=['name1'])
    motr.start('endpoint', create_process_fid(120), create_process_fid(15),
               profile)
    consumer._do_work(planner, motr)


def test_first_entrypoint_request_broadcasts_fail_first(
        mocker, planner, motr, consumer, consul_util):
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

    def my_get(key: str, recurse: bool = False):
        if key == 'm0conf/nodes' and recurse:
            return [
                new_kv(k, v) for k, v in [(
                    'm0conf/nodes/cmu/processes/6/services/ha',
                    '15'), (
                        'm0conf/nodes/cmu/processes/6/services/rm', '16'
                    ), ('m0conf/nodes/localhost/processes/7/services/rms',
                        '17')]
            ]
        elif key == 'm0conf/nodes/localhost/processes/7/services/rms':
            return new_kv('m0conf/nodes/localhost/processes/7/services/rms',
                          '17')
        raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

    def my_services(name):
        if name == 'confd':
            return [{
                'Node': 'localhost',
                'Service': 'confd',
                'ServiceID': '7',
                'Address': '192.168.0.28',
                'ServiceAddress': '192.168.0.28',
                'ServicePort': '12345'
            }]
        if name == 'hax':
            return [{
                'Node': 'localhost',
                'Service': 'hax',
                'ServiceID': '45',
                'Address': '192.168.0.28',
                'ServiceAddress': '192.168.0.28',
                'ServicePort': '667'
            }]
        raise RuntimeError(f'Unexpected call: name={name}')

    mocker.patch.object(consul_util.kv, 'kv_get', side_effect=my_get)
    mocker.patch.object(consul_util,
                        'get_leader_session_no_wait',
                        return_value='localhost')
    mocker.patch.object(consul_util,
                        'get_session_node',
                        return_value='localhost')

    mocker.patch.object(consul_util.catalog,
                        'get_services',
                        side_effect=my_services)

    msg = FirstEntrypointRequest(reply_context='stub',
                                 req_id=Uint128(0, 1),
                                 remote_rpc_endpoint='ep',
                                 process_fid=Fid(1, 6),
                                 git_rev='deadbeef',
                                 pid=123,
                                 is_first_request=True)
    run_in_consumer(mocker, msg, planner, consumer, motr)
    traces = motr._ffi.traces
    assert AssertionPlan(
        tr_and(tr_method('ha_broadcast'),
               ha_note_failed())).run(traces), 'M0_NC_FAILED not broadcast'
    assert AssertionPlan(
        tr_and(tr_method('ha_broadcast'),
               ha_note_failed())).and_then(
        tr_method('entrypoint_reply')).run(traces), \
        'entrypoint_reply should go after M0_NC_FAILED ' \
        'is broadcast'
