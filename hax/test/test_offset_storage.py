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

# flake8: noqa
import logging
import unittest
from time import sleep

from hax.queue.offset import OffsetStorage
from hax.util import ConsulKVBasic
from unittest.mock import Mock, MagicMock


class TestOffsetStorage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s {%(threadName)s} [%(levelname)s] %(message)s')

    def test_key_prefix_correct(self):
        kv = ConsulKVBasic()
        kv.kv_put = MagicMock()

        storage = OffsetStorage('my-node' , key_prefix='bq-delivered', kv=kv)
        storage.mark_last_read(150)

        kv.kv_put.assert_called_with('bq-delivered/my-node', '150')

    def test_key_prefix_used_everywhere(self):
        kv = ConsulKVBasic()
        kv.kv_put = MagicMock()
        kv.kv_get = MagicMock(side_effect=[{'Value': '120'}])

        storage = OffsetStorage('server1' , key_prefix='somequeue', kv=kv)
        storage.mark_last_read(120)
        epoch = storage.get_last_read_epoch()

        kv.kv_put.assert_called_with('somequeue/server1', '120')
        kv.kv_get.assert_called_with('somequeue/server1')
        self.assertEqual(120, epoch)
