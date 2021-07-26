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

import logging
from base64 import b64encode
from typing import List

import pytest
import simplejson
from hax.message import BroadcastHAStates
from hax.motr import WorkPlanner
from hax.motr.delivery import DeliveryHerald
from hax.server import ServerRunner
from hax.types import Fid, HAState, MessageId, ServiceHealth


@pytest.fixture
def herald(mocker):
    return DeliveryHerald()


@pytest.fixture
def planner(mocker) -> WorkPlanner:
    def fake_add(cmd):
        if hasattr(cmd, 'reply_to') and cmd.reply_to:
            cmd.reply_to.put([MessageId(1, 42)])

    planner = WorkPlanner()
    mocker.patch.object(planner, 'add_command', side_effect=fake_add)
    return planner


@pytest.fixture
async def hax_client(mocker, aiohttp_client, herald, planner, consul_util,
                     loop):
    srv = ServerRunner(planner, herald, consul_util)
    srv._configure()
    return await aiohttp_client(srv.app)


async def test_hello_works(hax_client):
    resp = await hax_client.get('/')
    assert resp.status == 200
    text = await resp.text()
    assert text == "I'm alive! Sincerely, HaX"


@pytest.mark.parametrize('status,health', [('passing', ServiceHealth.OK),
                                           ('warning', ServiceHealth.FAILED),
                                           ('critical', ServiceHealth.FAILED)])
async def test_service_health_broadcast(hax_client, planner, status: str,
                                        health: ServiceHealth):
    service_health = [{
        'Node': {
            'Node': 'localhost',
            'Address': '10.1.10.12',
        },
        'Service': {
            'ID': '12',
            'Service': 'ios',
            'Tags': [],
            'Port': 8000,
        },
        'Checks': [
            {
                'Node': '12',
                'CheckID': 'service:ios',
                'Name': "Service 'ios' check",
                'Status': status,
                'Notes': '',
                'Output': '',
                'ServiceID': '12',
                'ServiceName': 'ios',
            },
        ],
    }]
    resp = await hax_client.post('/', json=service_health)
    assert resp.status == 200
    assert planner.add_command.called
    planner.add_command.assert_called_once_with(
        BroadcastHAStates(
            states=[HAState(fid=Fid(0x7200000000000001, 12), status=health)],
            reply_to=None))


class ContainsStates:
    def __init__(self, pattern: List[HAState]):
        self.pattern = pattern

    def __repr__(self):
        return str(self.pattern)

    def __eq__(self, value):
        if not isinstance(value, BroadcastHAStates):
            return False
        return self.pattern == value.states


async def test_bq_stob_message_type_recognized(hax_client, planner, herald,
                                               consul_util, mocker):
    def fake_get(key):
        ret = {'bq-delivered/192.168.0.28': ''}
        return ret[key]

    mocker.patch.object(herald, 'wait_for_any')
    #
    # InboxFilter will try to read epoch - let's mock KV operations
    mocker.patch.object(consul_util.kv, 'kv_put')
    mocker.patch.object(consul_util.kv, 'kv_get', fake_get)
    event_payload = {
        'message_type': 'STOB_IOQ_ERROR',
        'payload': {
            'fid': '0x1:0x2',
            'conf_sdev': '0x1:0x4'
        }
    }
    event_str = simplejson.dumps(event_payload)
    b64: bytes = b64encode(event_str.encode())
    b64_str = b64.decode()

    payload = [{
        'Key': 'bq/12',
        'CreateIndex': 1793,
        'ModifyIndex': 1793,
        'LockIndex': 0,
        'Flags': 0,
        'Value': b64_str,
        'Session': ''
    }]
    # Test execution
    resp = await hax_client.post('/watcher/bq', json=payload)
    # Validate now
    if resp.status != 200:
        resp_json = await resp.json()
        logging.getLogger('hax').debug('Response: %s', resp_json)
    assert resp.status == 200
    planner.add_command.assert_called_once_with(
        ContainsStates(
            [HAState(fid=Fid(0x1, 0x4), status=ServiceHealth.FAILED)]))
