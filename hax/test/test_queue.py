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

# flake8: noqa
import json
import logging
import unittest
from hax.log import TRACE
from hax.message import ProcessKVUpdate
from hax.motr.planner import WorkPlanner
from hax.queue import BQProcessor
from hax.queue.publish import Publisher
from hax.types import Fid, HAState, ObjHealth
from hax.util import KVAdapter, TxPutKV, dump_json, ha_state_to_json
from unittest.mock import Mock, MagicMock


def transaction_helper(data):
    store = [('test_queue/1', '{"message_type": "dummy_type", "payload": {"key": "val"}}', 0),
             ('cached_key', 'True', 0)]

    for d in data:
        if d in store:
            return False
    return True


class TestPublisher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # It seems like when unittest is invoked from setup.py,
        # some default logging configuration is already applied;
        # invoking setup_logging() will make the log messages to appear twice.
        logging.addLevelName(TRACE, 'TRACE')
        logging.getLogger('hax').setLevel(TRACE)

    def test_publish_no_duplicate(self):
        kv = KVAdapter(cns=MagicMock())

        publisher = Publisher('test_queue', kv)
        publisher.kv.kv_put_in_transaction =  Mock(side_effect=transaction_helper)
        payload = dump_json({'key':'val'})
        ans = publisher.publish_no_duplicate('dummy_type', payload, '2')
        self.assertTrue(ans)

    def test_publish_duplicate(self):
        kv = KVAdapter(cns=MagicMock())

        publisher = Publisher('test_queue', kv)
        publisher.kv.kv_put_in_transaction =  Mock(side_effect=transaction_helper)
        payload = dump_json({'key':'val'})
        ans = publisher.publish_no_duplicate('dummy_type', payload, '1')
        self.assertFalse(ans)

    def test_publish_duplicate_with_checks(self):
        kv = KVAdapter(cns=MagicMock())

        publisher = Publisher('test_queue', kv)
        publisher.kv.kv_put_in_transaction =  Mock(side_effect=transaction_helper)
        payload = dump_json({'key':'val'})
        checks = [TxPutKV(key='cached_key', value='True', cas=0)]
        ans = publisher.publish_no_duplicate('dummy_type', payload, '2', checks)
        self.assertFalse(ans)


class TestBQProcessor(unittest.TestCase):
    # todo can be changed to check payload processed.. and assert for all calls
    def test_valid_payload_process_handlers(self):
        mm = MagicMock()
        bqprocessor = BQProcessor(mm, mm, mm, mm)
        bqprocessor.handle_process_kv_update = MagicMock()
        payload = {
            'message_type' : 'PROCESS_KV_UPDATE',
            'payload' : 'dummy'
        }
        bqprocessor.payload_process(dump_json(payload))
        bqprocessor.handle_process_kv_update.assert_called()

    def test_payload_process_invalid_handlers(self):
        mm = MagicMock()
        bqprocessor = BQProcessor(mm, mm, mm, mm)
        payload = {
            'message_type' : 'unsupported type',
            'payload' : 'dummy'
        }
        with self.assertLogs('hax', level='WARNING') as log:
            bqprocessor.payload_process(dump_json(payload))


    def test_invalid_payload_process(self):
        mm = MagicMock()
        bqprocessor = BQProcessor(mm, mm, mm, mm)
        payload = ''

        with self.assertLogs('hax', level='ERROR') as log:
            bqprocessor.payload_process(payload)

    def test_process_kv_update(self):
        def fake_add(cmd):
            self.assertIsInstance(cmd, ProcessKVUpdate)

        mm = MagicMock()
        planner = WorkPlanner()
        bqprocessor = BQProcessor(planner, mm, mm, mm)
        planner.add_command = Mock(side_effect=fake_add)
        process_fid = Fid(0x7200000000000001, 0x6)
        payload = ha_state_to_json(HAState(fid=process_fid,
                                           status=ObjHealth.OFFLINE))
        bqprocessor.handle_process_kv_update(json.loads(payload))

    def test_process_kv_update_invalid_payload(self):
        mm = MagicMock()
        bqprocessor = BQProcessor(mm, mm, mm, mm)
        payload = {
            'invalid_key':None
        }
        with self.assertLogs('hax', level='ERROR') as log:
            bqprocessor.handle_process_kv_update(payload)
