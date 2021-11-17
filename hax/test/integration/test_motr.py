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
import json
import logging
from typing import Any, Callable

import pytest

from hax.handler import ConsumerThread
from hax.message import (BaseMessage, Die, FirstEntrypointRequest,
                         HaNvecGetEvent, StobId, StobIoqError)
from hax.motr import Motr, WorkPlanner
from hax.motr.delivery import DeliveryHerald
from hax.motr.ffi import HaxFFI
from hax.types import (Fid, FidStruct, HaNote, HaNoteStruct, HAState, Profile,
                       ServiceHealth, Uint128)
from hax.util import create_process_fid, create_profile_fid, dump_json

from .testutils import (AssertionPlan, FakeFFI, Invocation, TraceMatcher,
                        tr_and, tr_method, tr_not)


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


def contains_drive() -> TraceMatcher:
    '''
    Returns true if the second argument is a array to pointer to HaNoteStruct
    and it contains a FID with DRIVE f_container value in array.

    It makes sense to use this matcher together with
    `tr_method('ha_broadcast')`
    '''
    def fn(trace: Invocation) -> bool:
        if len(trace.args) < 2:
            return False
        notes = trace.args[1]
        if (not isinstance(notes, ctypes.Array)):
            return False

        for note in notes:
            if not isinstance(note, HaNoteStruct):
                return False
            fid = note.no_id
            if fid.f_container == 0x6b00000000000001:
                logging.debug('Found DRIVE FID type: %s', fid)
                return True

        return False

    return fn


def node_failed() -> TraceMatcher:
    '''
    Returns true if the second argument is a array to pointer to HaNoteStruct
    and it contains 5 elements and that structure brings M0_NC_FAILED state.
    In case of node failure we should see 5 elements(1 IO service, 1 node fid,
    1 encl fid, 2 ctrls) in array.

    It makes sense to use this matcher together with
    `tr_method('ha_broadcast')`
    '''
    def fn(trace: Invocation) -> bool:
        if len(trace.args) < 2:
            return False
        notes = trace.args[1]
        if (not isinstance(notes, ctypes.Array) or len(notes) != 5):
            return False

        fids = [
            FidStruct(0x7200000000000001, 0x15),
            FidStruct(0x6500000000000001, 0x4),
            FidStruct(0x6e00000000000001, 0x3),
            FidStruct(0x6300000000000001, 0x5),
            FidStruct(0x6300000000000001, 0x6)
        ]

        for _, note in enumerate(notes):
            if not isinstance(note, HaNoteStruct):
                return False
            state: int = note.no_state
            if state != HaNoteStruct.M0_NC_FAILED:
                return False
            fid = note.no_id
            bMatch = False
            for i, out_fid in enumerate(fids):
                if (fid.f_container == out_fid.f_container
                        and fid.f_key == out_fid.f_key):
                    bMatch = True
                    del fids[i]
                    break

            if not bMatch:
                return False

        # fids is empty -> all required fids were found
        return not fids

    return fn


def node_fid_failed() -> TraceMatcher:
    '''
    Returns true if node fid failure is present in trace
    '''
    def fn(trace: Invocation) -> bool:
        if len(trace.args) < 2:
            return False
        notes = trace.args[1]
        if not isinstance(notes, ctypes.Array):
            return False

        node_fid = FidStruct(0x6e00000000000001, 0x3)

        for _, note in enumerate(notes):
            if not isinstance(note, HaNoteStruct):
                return False
            fid = note.no_id
            if (fid.f_container == node_fid.f_container
                    and fid.f_key == node_fid.f_key):
                return True

        return False

    return fn


def io_service_failed() -> TraceMatcher:
    '''
    Returns true if the second argument is a pointer to HaNoteStruct and that
    structure brings M0_NC_FAILED state, also matched fid.

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
        fid = FidStruct(0x7200000000000001, 0x15)

        state: int = ptr.contents.no_state
        if (state != HaNoteStruct.M0_NC_FAILED
                or fid.f_container != ptr.contents.no_id.f_container
                or fid.f_key != ptr.contents.no_id.f_key):
            return False
        return True

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

    def my_get(key: str, recurse: bool = False, **kwds):
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
               ha_note_failed())).exists(traces), 'M0_NC_FAILED not broadcast'
    assert AssertionPlan(
        tr_and(tr_method('ha_broadcast'),
               ha_note_failed())).and_then(
        tr_method('entrypoint_reply')).exists(traces), \
        'entrypoint_reply should go after M0_NC_FAILED ' \
        'is broadcast'


def test_get_nvec_replies_something(
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

    def my_get(key: str, recurse: bool = False, **kwds):
        if key == 'm0conf/nodes' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "offline"
                  })), ('m0conf/nodes/cmu/processes/21/services/rm', '16'),
                 ('m0conf/nodes/localhost/processes/21/services/rms', '17'),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001:0x10',
                  json.dumps({
                      "name": "rms",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001:0x10'
                  '/sdevs/0x6400000000000001:0x20',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0xa/services/0x7300000000000001:0xc',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif key == 'm0conf/nodes/localhost/processes/7/services/rms':
            return new_kv('m0conf/nodes/localhost/processes/7/services/rms',
                          '17')
        elif key == 'm0conf/nodes/0x6e00000000000001:0x3':
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3',
                json.dumps({
                    "name": "localhost",
                    "state": "M0_NC_UNKNOWN"
                }))
        elif key == 'm0conf/sites' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x5',
                  json.dumps({"state": "M0_NC_UNKNOWN"})),
                 ('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x6/drives'
                  '/0x6b00000000000001:0x2d',
                  json.dumps({"sdev": "0x6400000000000001:0x20"})),
                 ('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x6',
                  json.dumps({"state": "M0_NC_UNKNOWN"}))]
            ]
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

    patch = mocker.patch.object
    patch(consul_util.kv, 'kv_get', side_effect=my_get)
    patch(consul_util, 'get_leader_session_no_wait', return_value='localhost')
    patch(consul_util, 'get_session_node', return_value='localhost')

    patch(consul_util.catalog, 'get_services', side_effect=my_services)
    patch(consul_util, 'get_node_health_status', return_value='passing')
    patch(consul_util, 'get_service_health', return_value=ServiceHealth.OK)

    msg = HaNvecGetEvent(
        hax_msg=12,
        nvec=[
            HaNote(obj_t='SERVICE',
                   note=HaNoteStruct(
                       no_id=Fid.parse('0x7300000000000001:0x10').to_c(),
                       no_state=5)),
            HaNote(obj_t='PROCESS',
                   note=HaNoteStruct(
                       no_id=Fid.parse('0x7200000000000001:0x15').to_c(),
                       no_state=5)),
            HaNote(obj_t='DRIVE',
                   note=HaNoteStruct(
                       no_id=Fid.parse('0x6b00000000000001:0x2d').to_c(),
                       no_state=5)),
            HaNote(obj_t='CONTROLLER',
                   note=HaNoteStruct(
                       no_id=Fid.parse('0x6300000000000001:0x5').to_c(),
                       no_state=5))
        ])
    run_in_consumer(mocker, msg, planner, consumer, motr)
    traces = motr._ffi.traces
    assert AssertionPlan(
        tr_method('ha_nvec_reply')).exists(traces), 'ha_nvec_reply not invoked'


def test_broadcast_node_failure(mocker, motr, consul_util):
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

    def my_get(key: str, recurse: bool = False, **kwds):
        if key == 'm0conf/nodes' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "offline"
                  })), ('m0conf/nodes/cmu/processes/6/services/rm', '16'),
                 ('m0conf/nodes/localhost/processes/7/services/rms', '17'),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001:0x17',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0xa/services/0x7300000000000001:0xc',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3',
                  json.dumps({
                      "name": "localhost",
                      "state": "M0_NC_FAILED"
                  }))]
            ]
        elif key == 'm0conf/sites' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x5',
                  json.dumps({"state": "M0_NC_FAILED"})),
                 ('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x6',
                  json.dumps({"state": "M0_NC_FAILED"}))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3'
              '/processes' and recurse):
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001:0x17',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0xa/services/0x7300000000000001:0xc',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0x15' and recurse):
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001'
                  ':0x17', json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0x15'):
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3/processes'
                '/0x7200000000000001:0x15',
                json.dumps({
                    "name": "m0_server",
                    "state": "failed"
                }))
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0xa'):
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3/processes'
                '/0x7200000000000001:0xa',
                json.dumps({
                    "name": "m0_server",
                    "state": "failed"
                }))
        elif key == 'm0conf/nodes/localhost/processes/7/services/rms':
            return new_kv('m0conf/nodes/localhost/processes/7/services/rms',
                          '17')
        elif key == 'localhost/processes/0x7200000000000001:0x15':
            return new_kv(
                'localhost/processes/0x7200000000000001',
                json.dumps({
                    'type': 'M0_CONF_HA_PROCESS_OTHER',
                    'state': 'Unknown'
                }))
        elif key == 'm0conf/nodes/0x6e00000000000001:0x3':
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3',
                json.dumps({
                    "name": "localhost",
                    "state": "M0_NC_UNKNOWN"
                }))
        raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

    mocker.patch.object(consul_util.kv, 'kv_get', side_effect=my_get)
    mocker.patch.object(consul_util.kv, 'kv_put', return_value=0)
    mocker.patch.object(consul_util,
                        'get_node_fid',
                        return_value=Fid(0x6e00000000000001, 0x3))

    mocker.patch.object(consul_util,
                        'get_node_encl_fid',
                        return_value=Fid(0x6500000000000001, 0x4))

    motr.broadcast_ha_states([
        HAState(fid=Fid(0x7200000000000001, 0x15), status=ServiceHealth.FAILED)
    ])

    traces = motr._ffi.traces
    assert AssertionPlan(
        tr_and(tr_method('ha_broadcast'),
               node_failed())).exists(traces), 'Node failure not broadcast'


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


def create_stub_get(process_type: str) -> Callable[[str, bool], Any]:
    def my_get(key: str, recurse: bool = False, **kwds):
        if key == 'm0conf/nodes' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "offline"
                  })), ('m0conf/nodes/cmu/processes/21/services/rm', '16'),
                 ('m0conf/nodes/localhost/processes/21/services/rms', '17'),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001:0x10',
                  json.dumps({
                      "name": "rms",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001:0x10'
                  '/sdevs/0x6400000000000001:0x20',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0xa/services/0x7300000000000001:0xc',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif key == 'm0conf/sites' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x5',
                  json.dumps({"state": "M0_NC_UNKNOWN"})),
                 ('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x6/drives'
                  '/0x6b00000000000001:0x2d',
                  json.dumps({"sdev": "0x6400000000000001:0x20"})),
                 ('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x6',
                  json.dumps({"state": "M0_NC_UNKNOWN"}))]
            ]
        elif key == 'localhost/processes/0x7200000000000001:0x15':
            return new_kv(
                'localhost/processes/0x7200000000000001',
                json.dumps({
                    'type': process_type,
                    'state': 'Unknown'
                }))
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3'
              '/processes' and recurse):
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001:0x17',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0xa/services/0x7300000000000001:0xc',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0x15' and recurse):
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001'
                  ':0x17', json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0x15'):
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3/processes'
                '/0x7200000000000001:0x15',
                json.dumps({
                    "name": "m0_server",
                    "state": "failed"
                }))
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0xa'):
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3/processes'
                '/0x7200000000000001:0xa',
                json.dumps({
                    "name": "m0_server",
                    "state": "failed"
                }))
        elif key == 'm0conf/nodes/localhost/processes/7/services/rms':
            return new_kv('m0conf/nodes/localhost/processes/7/services/rms',
                          '17')
        elif key == 'm0conf/nodes/0x6e00000000000001:0x3':
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3',
                json.dumps({
                    "name": "localhost",
                    "state": "M0_NC_UNKNOWN"
                }))
        raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

    return my_get


def test_mkfs_process_stopped_no_disk_marked_offline(mocker, motr,
                                                     consul_util):
    mocker.patch.object(
        consul_util.kv,
        'kv_get',
        side_effect=create_stub_get('M0_CONF_HA_PROCESS_M0MKFS'))
    mocker.patch.object(consul_util.kv, 'kv_put', return_value=0)
    mocker.patch.object(consul_util, 'update_drive_state')
    mocker.patch.object(consul_util,
                        'get_node_fid',
                        return_value=Fid(0x6e00000000000001, 0x3))
    mocker.patch.object(consul_util,
                        'get_node_encl_fid',
                        return_value=Fid(0x6500000000000001, 0x4))

    motr.broadcast_ha_states([
        HAState(fid=Fid(0x7200000000000001, 0x15), status=ServiceHealth.FAILED)
    ])

    assert not consul_util.update_drive_state.called, \
        'The drive state should not be updated when MKFS stops'

    traces = motr._ffi.traces
    assert AssertionPlan(
        tr_and(tr_method('ha_broadcast'),
               tr_not(contains_drive()))).exists(traces), \
        'DRIVE should not be broadcast when MKFS is stopped'


def test_nonmkfs_process_stop_causes_drive_offline(mocker, motr, consul_util):
    mocker.patch.object(consul_util.kv,
                        'kv_get',
                        side_effect=create_stub_get('M0_CONF_HA_PROCESS_M0D'))
    mocker.patch.object(consul_util.kv, 'kv_put', return_value=0)
    mocker.patch.object(consul_util, 'update_drive_state')
    mocker.patch.object(consul_util,
                        'get_node_fid',
                        return_value=Fid(0x6e00000000000001, 0x3))
    mocker.patch.object(consul_util,
                        'get_node_encl_fid',
                        return_value=Fid(0x6500000000000001, 0x4))

    motr.broadcast_ha_states([
        HAState(fid=Fid(0x7200000000000001, 0x15), status=ServiceHealth.FAILED)
    ])

    assert consul_util.update_drive_state.called, \
        'The drive state should be updated in Consul KV'

    traces = motr._ffi.traces
    assert AssertionPlan(
        tr_and(tr_method('ha_broadcast'),
               contains_drive())).exists(traces), \
        'DRIVE must be broadcast when non-MKFS process is stopped'


def test_broadcast_io_service_failure(mocker, planner, motr, consumer,
                                      consul_util):
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

    def my_get(key: str, recurse: bool = False, **kwds):
        if key == 'm0conf/nodes' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "offline"
                  })), ('m0conf/nodes/cmu/processes/6/services/rm', '16'),
                 ('m0conf/nodes/localhost/processes/7/services/rms', '17'),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services'
                  '/0x7300000000000001:0x17',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0xa/services/0x7300000000000001'
                  ':0xc', json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif key == 'm0conf/sites' and recurse:
            return [
                new_kv(k, v) for k, v in
                [('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x5',
                  json.dumps({"state": "M0_NC_UNKNOWN"})),
                 ('m0conf/sites/0x5300000000000001:0x1/racks'
                  '/0x6100000000000001:0x2/encls/0x6500000000000001:0x4'
                  '/ctrls/0x6300000000000001:0x6',
                  json.dumps({"state": "M0_NC_UNKNOWN"}))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3'
              '/processes' and recurse):
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001'
                  ':0x17', json.dumps({
                      "name": "ios",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0xa/services/0x7300000000000001:0xc',
                  json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0x15' and recurse):
            return [
                new_kv(k, v) for k, v in
                [('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15',
                  json.dumps({
                      "name": "m0_server",
                      "state": "failed"
                  })),
                 ('m0conf/nodes/0x6e00000000000001:0x3/processes'
                  '/0x7200000000000001:0x15/services/0x7300000000000001'
                  ':0x17', json.dumps({
                      "name": "ios",
                      "state": "failed"
                  }))]
            ]
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0x15'):
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3/processes'
                '/0x7200000000000001:0x15',
                json.dumps({
                    "name": "m0_server",
                    "state": "failed"
                }))
        elif (key == 'm0conf/nodes/0x6e00000000000001:0x3/processes'
              '/0x7200000000000001:0xa'):
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3/processes'
                '/0x7200000000000001:0xa',
                json.dumps({
                    "name": "m0_server",
                    "state": "online"
                }))
        elif key == 'm0conf/nodes/localhost/processes/7/services/rms':
            return new_kv('m0conf/nodes/localhost/processes/7/services/rms',
                          '17')
        elif key == 'localhost/processes/0x7200000000000001:0x15':
            return new_kv(
                'localhost/processes/0x7200000000000001',
                json.dumps({
                    'type': 'M0_CONF_HA_PROCESS_OTHER',
                    'state': 'Unknown'
                }))
        elif key == 'm0conf/nodes/0x6e00000000000001:0x3':
            return new_kv(
                'm0conf/nodes/0x6e00000000000001:0x3',
                json.dumps({
                    "name": "localhost",
                    "state": "M0_NC_UNKNOWN"
                }))
        raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

    mocker.patch.object(consul_util.kv, 'kv_get', side_effect=my_get)
    # TODO: Handle 'kv_put' by updating kv returned by 'kv_get'
    mocker.patch.object(consul_util.kv, 'kv_put', return_value=0)
    mocker.patch.object(consul_util,
                        'get_node_fid',
                        return_value=Fid(0x6e00000000000001, 0x3))
    mocker.patch.object(consul_util,
                        'get_node_encl_fid',
                        return_value=Fid(0x6500000000000001, 0x4))

    motr.broadcast_ha_states([
        HAState(fid=Fid(0x7200000000000001, 0x15), status=ServiceHealth.FAILED)
    ])

    traces = motr._ffi.traces
    assert AssertionPlan(tr_and(
        tr_method('ha_broadcast'),
        io_service_failed())).exists(traces), 'IOservice failure not broadcast'
    assert AssertionPlan(tr_and(tr_method('ha_broadcast'),
                                node_fid_failed())).not_exists(traces), \
        'Node failure should not be broadcast'


# flake8: noqa


def test_bq_stob_serializeable():
    stob = StobId(Fid(12, 13), Fid(14, 15))
    msg = StobIoqError(fid=Fid(5, 6),
                       conf_sdev=Fid(1, 2),
                       stob_id=stob,
                       fd=42,
                       opcode=4,
                       rc=2,
                       offset=0xBF,
                       size=100,
                       bshift=4)
    first = dump_json(stob)
    assert first == '{"domain_fid": "0xc:0xd", "fid": "0xe:0xf"}'
    second = dump_json(msg)
    assert second == '{"fid": "0x5:0x6", "conf_sdev": "0x1:0x2", "stob_id": {"domain_fid": "0xc:0xd", "fid": "0xe:0xf"}, "fd": 42, "opcode": 4, "rc": 2, "offset": 191, "size": 100, "bshift": 4}'
