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
from threading import Condition, Thread
from time import sleep, time

from hax.exception import NotDelivered
from hax.log import TRACE
from hax.motr.delivery import DeliveryHerald
from hax.types import HaLinkMessagePromise, MessageId

LOG = logging.getLogger('hax')


class CountDownLatch:

    """ Home-made implementation of CountDownLatch from Java world.

    Unblocks a single thread when all N threads have invoked count_down()
    from their sides.
    """
    def __init__(self, value: int):
        """CountDownLatch with countdown value."""
        self.lock = Condition()
        self.value = value

    def count_down(self):
        with self.lock:
            if self.value == 0:
                raise RuntimeError("Already zero, nothing to count down")
            self.value -= 1
            if self.value == 0:
                self.lock.notifyAll()

    def waitfor(self):
        while True:
            with self.lock:
                if not self.value:
                    return
                self.lock.wait()


class TestDeliveryHeraldAny(unittest.TestCase):
    """
    Tests wait_for_any() functionality.
    """
    @classmethod
    def setUpClass(cls):
        # It seems like when unittest is invoked from setup.py,
        # some default logging configuration is already applied;
        # invoking setup_logging() will make the log messages to appear twice.
        logging.addLevelName(TRACE, 'TRACE')
        logging.getLogger('hax').setLevel(TRACE)

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

    def test_if_delivered_earlier_than_awaited_wait_works(self):
        herald = DeliveryHerald()
        notified_ok = True
        thread_count = 1
        latch = CountDownLatch(thread_count)

        def fn(msg: MessageId):
            try:
                LOG.debug('Thread started')
                herald.notify_delivered(msg)
                LOG.debug('Notified delivery %s', msg)
                latch.count_down()
                LOG.debug('Main thread unblocked')

            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        threads = [
            Thread(target=fn, args=(MessageId(100, i + 1), ))
            for i in range(thread_count)
        ]

        for t in threads:
            t.start()
        # Block until all the threads come to latch.count_down() and thus
        # the message is notified for sure
        latch.waitfor()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            herald.wait_for_any(HaLinkMessagePromise([m(1)]), timeout_sec=2)
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
        self.assertEqual(0, len(herald.unsorted_deliveries.keys()))

    def test_if_delivered_earlier_than_awaited_works_immediately(self):
        herald = DeliveryHerald()
        notified_ok = True
        thread_count = 1
        latch = CountDownLatch(thread_count)

        def fn(msg: MessageId):
            try:
                LOG.debug('Thread started')
                herald.notify_delivered(msg)
                LOG.debug('Notified delivery %s', msg)
                latch.count_down()
                LOG.debug('Main thread unblocked')

            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        threads = [
            Thread(target=fn, args=(MessageId(100, i + 1), ))
            for i in range(thread_count)
        ]

        for t in threads:
            t.start()
        # Block until all the threads come to latch.count_down() and thus
        # the message is notified for sure
        latch.waitfor()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            started = time()
            herald.wait_for_any(HaLinkMessagePromise([m(1)]), timeout_sec=5)
            finished = time()
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
        self.assertLess(
            finished - started, 5,
            'Awaiting thread was unblocked only by a timeout. It means '
            'that unsorted_deliveries was analyzed too late.'
        )

    def test_if_delivered_earlier_than_awaited_wait_many(self):
        herald = DeliveryHerald()
        notified_ok = True
        thread_count = 6
        latch = CountDownLatch(thread_count)

        def fn(msg: MessageId):
            try:
                LOG.debug('Thread started')
                herald.notify_delivered(msg)
                LOG.debug('Notified delivery %s', msg)
                latch.count_down()
                LOG.debug('Main thread unblocked')

            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        threads = [
            Thread(target=fn, args=(MessageId(100, i + 1), ))
            for i in range(thread_count)
        ]

        for t in threads:
            t.start()
        # Block until all the threads come to latch.count_down() and thus
        # the message is notified for sure
        latch.waitfor()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            herald.wait_for_any(HaLinkMessagePromise([m(1), m(5)]),
                                timeout_sec=2)
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
        self.assertEqual(4, len(herald.unsorted_deliveries.keys()))


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

    def test_if_delivered_earlier_than_awaited_wait_works(self):
        herald = DeliveryHerald()
        notified_ok = True
        thread_count = 1
        latch = CountDownLatch(thread_count)

        def fn(msg: MessageId):
            try:
                LOG.debug('Thread started')
                herald.notify_delivered(msg)
                LOG.debug('Notified delivery %s', msg)
                latch.count_down()
                LOG.debug('Main thread unblocked')

            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        threads = [
            Thread(target=fn, args=(MessageId(100, i + 1), ))
            for i in range(thread_count)
        ]

        for t in threads:
            t.start()
        # Block until all the threads come to latch.count_down() and thus
        # the message is notified for sure
        latch.waitfor()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            herald.wait_for_all(HaLinkMessagePromise([m(1)]), timeout_sec=2)
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
        self.assertEqual(0, len(herald.unsorted_deliveries.keys()))

    def test_if_delivered_earlier_than_awaited_wait_many(self):
        herald = DeliveryHerald()
        notified_ok = True
        thread_count = 6
        latch = CountDownLatch(thread_count)

        def fn(msg: MessageId):
            try:
                LOG.debug('Thread started')
                herald.notify_delivered(msg)
                LOG.debug('Notified delivery %s', msg)
                latch.count_down()
                LOG.debug('Main thread unblocked')

            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        threads = [
            Thread(target=fn, args=(MessageId(100, i + 1), ))
            for i in range(thread_count)
        ]

        for t in threads:
            t.start()
        # Block until all the threads come to latch.count_down() and thus
        # the message is notified for sure
        latch.waitfor()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            herald.wait_for_all(HaLinkMessagePromise([m(1), m(5)]),
                                timeout_sec=2)
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
        self.assertEqual(4, len(herald.unsorted_deliveries.keys()))

    def test_if_delivered_earlier_than_awaited_notified_immediately(self):
        herald = DeliveryHerald()
        notified_ok = True
        thread_count = 1
        latch = CountDownLatch(thread_count)

        def fn(msg: MessageId):
            try:
                LOG.debug('Thread started')
                herald.notify_delivered(msg)
                LOG.debug('Notified delivery %s', msg)
                latch.count_down()
                LOG.debug('Main thread unblocked')

            except:
                logging.exception('*** ERROR ***')
                notified_ok = False

        threads = [
            Thread(target=fn, args=(MessageId(100, i + 1), ))
            for i in range(thread_count)
        ]

        for t in threads:
            t.start()
        # Block until all the threads come to latch.count_down() and thus
        # the message is notified for sure
        latch.waitfor()

        def m(x):
            return MessageId(halink_ctx=100, tag=x)

        try:
            started = time()
            herald.wait_for_all(HaLinkMessagePromise([m(1)]),
                                timeout_sec=2)
            finished = time()
        finally:
            for t in threads:
                t.join()
        self.assertTrue(notified_ok,
                        'Unexpected exception appeared in notifier thread')
        self.assertLess(
            finished - started, 5,
            'Awaiting thread was unblocked only by a timeout. It means '
            'that unsorted_deliveries was analyzed too late.'
        )
