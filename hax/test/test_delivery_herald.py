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
from hax.motr import log_exception
from hax.motr.delivery import DeliveryHerald
from hax.types import HaLinkMessagePromise, MessageId


class TestDeliveryHeraldAny(unittest.TestCase):
    """
    Tests wait_for_any() functionality.
    """
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
                            timeout_sec=10)
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
        try:
            with self.assertRaises(NotDelivered):
                herald.wait_for_any(HaLinkMessagePromise(
                    [m(42, 1), m(42, 3), m(42, 4)]),
                                    timeout_sec=5)
        finally:
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

        threads = [
            Thread(target=fn, args=(MessageId(100, i), ))
            for i in range(1, 32)
        ]
        for t in threads:
            t.start()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            herald.wait_for_any(HaLinkMessagePromise(
                [m(99), m(25), m(28), m(31)]),
                                timeout_sec=5)
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')


class TestDeliveryHeraldAll(unittest.TestCase):
    """
    Tests wait_for_all() functionality.
    """
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
        herald.wait_for_all(HaLinkMessagePromise([m(100, 1)]), timeout_sec=5)
        t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')

    def test_exception_raised_if_not_all_delivered(self):
        herald = DeliveryHerald()
        notified_ok = True

        def fn():
            try:
                sleep(1.5)
                herald.notify_delivered(MessageId(halink_ctx=42, tag=3))
            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        t = Thread(target=fn)
        t.start()

        m = MessageId
        try:
            with self.assertRaises(NotDelivered):
                herald.wait_for_all(HaLinkMessagePromise([m(42, 1),
                                                          m(42, 3)]),
                                    timeout_sec=5)
        finally:
            t.join()

        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')

    def test_works_if_all_messages_confirmed(self):
        herald = DeliveryHerald()
        notified_ok = True

        def fn():
            try:
                sleep(1.5)
                herald.notify_delivered(MessageId(halink_ctx=42, tag=3))
                herald.notify_delivered(MessageId(halink_ctx=42, tag=1))
            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        t = Thread(target=fn)
        t.start()

        m = MessageId
        try:
            herald.wait_for_all(HaLinkMessagePromise([m(42, 1),
                                                      m(42, 3)]),
                                timeout_sec=5)
        finally:
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

        threads = [
            Thread(target=fn, args=(MessageId(100, i), ))
            for i in range(1, 32)
        ]
        for t in threads:
            t.start()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            herald.wait_for_all(HaLinkMessagePromise(
                [m(5), m(25), m(28), m(31)]),
                                timeout_sec=5)
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
