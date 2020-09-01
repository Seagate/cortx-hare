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
import sys
import unittest
from threading import Thread
from time import sleep

from hax.exception import NotDelivered
from hax.motr.delivery import DeliveryHerald
from hax.types import HaLinkMessagePromise, MessageId


class TestDeliveryHerald(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.basicConfig(
            level=logging.DEBUG,
            stream=sys.stdout,
            format='%(asctime)s {%(threadName)s} [%(levelname)s] %(message)s')

    def test_it_works(self):
        herald = DeliveryHerald()
        notified_ok = True

        def fn():
            try:
                sleep(1.5)
                herald.notify_delivered(MessageId(halink_ctx=100, tag=1))
            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        t = Thread(target=fn)
        t.start()

        m = MessageId
        herald.wait_for_any(HaLinkMessagePromise(
            [m(100, 1), m(100, 3), m(100, 4)]),
                            timeout_sec=5)
        t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')

    def test_exception_raised_by_timeout(self):
        herald = DeliveryHerald()
        notified_ok = True

        def fn():
            try:
                sleep(1.5)
                herald.notify_delivered(MessageId(halink_ctx=43, tag=3))
            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        t = Thread(target=fn)
        t.start()

        m = MessageId
        with self.assertRaises(NotDelivered):
            herald.wait_for_any(HaLinkMessagePromise(
                [m(42, 1), m(42, 3), m(42, 4)]),
                                timeout_sec=5)
        t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')

    def test_works_under_load(self):
        herald = DeliveryHerald()
        notified_ok = True

        def fn(msg: MessageId):
            try:
                sleep(1.5)
                herald.notify_delivered(msg)
            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        threads = [Thread(target=fn, args=(MessageId(100, i), )) for i in range(1, 32)]
        for t in threads:
            t.start()

        m = lambda x: MessageId(halink_ctx=100, tag = x)
        herald.wait_for_any(HaLinkMessagePromise([m(99), m(25), m(28), m(31)]), timeout_sec=5)
        for t in threads:
            t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
