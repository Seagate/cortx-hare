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

import logging
import time
from threading import Condition, Lock
from typing import Dict, List

from hax.exception import NotDelivered
from hax.log import TRACE
from hax.types import HaLinkMessagePromise, MessageId

LOG = logging.getLogger('hax')

# 10 seconds is the max time for the messages that nobody has started awaiting.
MAX_UNSORTED_TTL = 10000


class DeliveryHerald:
    """
    Thread synchronizing block that implements the following use case:
    - Some message is sent from Python land to Motr
    - And the Python code needs to wait until a delivery is confirmed by Motr.

    Parameters:
        unsorted_ttl_msec - time-to-live threshold for unsorted_deliveries.
                            unsorted_deliveries stores the delivery
                            notifications for all deliveries that have no
                            awaiting client (probably because of race condition
                            e.g. if delivery happens faster than Python code
                            would start awaiting). unsorted_deliveries that are
                            kept unawaited longer than this TTL will be removed
                            from memory.

    Typical usage is as follows (assuming that delivery_herald is a singleton):

        tag_list = ffi.ha_broadcast(_ha_ctx, make_array(HaNoteStruct, notes),
                                    len(notes))
        delivery_herald.wait_for_any(HaLinkMessagePromise(tag_list))
        # if we are here then the delivery was confirmed
    """
    def __init__(self, unsorted_ttl_msec: int = MAX_UNSORTED_TTL):
        """Inits DeliveryHerald.

        Args:
            unsorted_ttl_msec (int): time-to-live threshold for
                unsorted_deliveries.
        """
        self.recently_delivered: Dict[HaLinkMessagePromise,
                                      List[MessageId]] = {}
        self.waiting_clients: Dict[HaLinkMessagePromise, Condition] = {}
        self.unsorted_deliveries: Dict[MessageId, int] = {}
        self.unsorted_ttl = unsorted_ttl_msec
        self.lock = Lock()

    def _verify_delivered(self, promise: HaLinkMessagePromise,
                          timeout_sec: float):
        """
        Verify if any message in promise._ids are reported by Motr
        as delivered. Calling function should hold the self.lock.
        """

        del self.waiting_clients[promise]
        if promise not in self.recently_delivered:
            raise NotDelivered('None of message tags =' + str(promise) +
                               '  were delivered to Motr within ' +
                               str(timeout_sec) + ' seconds timeout')
        confirmed_msgs = self.recently_delivered.pop(promise)
        LOG.log(TRACE, 'Thread unblocked - %s just received', confirmed_msgs)
        promise.exclude_ids(confirmed_msgs)

    def get_now_ts(self) -> int:
        """
        Returns the current timestamp in milliseconds.
        """
        return round(time.time() * 1000)

    def wait_for_any(self,
                     promise: HaLinkMessagePromise,
                     timeout_sec: float = 30.0):
        """
        Blocks the current thread until at least one of the messages in
        promise._ids are reported by Motr as delivered.

        Raises NotDelivered exception when timeout_sec exceeds.
        """
        condition = Condition()
        skip_await = False
        with self.lock:
            self.groom_unsorted(promise)
            self.waiting_clients[promise] = condition
            skip_await = promise in self.recently_delivered

        if skip_await:
            LOG.log(TRACE,
                    'Promise %s has been confirmed before, no need to block',
                    promise)
        else:
            with condition:
                LOG.log(TRACE, 'Blocking until %s is confirmed', promise)
                condition.wait(timeout=timeout_sec)
        with self.lock:
            self._verify_delivered(promise, timeout_sec)

    def wait_for_all(self,
                     promise: HaLinkMessagePromise,
                     timeout_sec: float = 30.0):
        """
        Blocks the current thread until all of the messages in
        promise._ids are reported by Motr as delivered.

        Raises NotDelivered exception when timeout_sec exceeds.
        """

        condition = Condition()
        skip_await = False

        with self.lock:
            self.groom_unsorted(promise)
            self.waiting_clients[promise] = condition
            skip_await = promise in self.recently_delivered

        while not promise.is_empty():
            if skip_await:
                LOG.log(
                    TRACE, 'Promise %s has been confirmed before, '
                    'no need to block', promise)
                skip_await = False
            else:
                with condition:
                    LOG.log(TRACE, 'Blocking until %s is confirmed', promise)
                    condition.wait(timeout=timeout_sec)
            with self.lock:
                self._verify_delivered(promise, timeout_sec)
                if not promise.is_empty():
                    self.waiting_clients[promise] = condition

    def groom_unsorted(self, promise: HaLinkMessagePromise) -> None:
        LOG.log(TRACE, 'Grooming by promise %s', promise)
        delivered: List[MessageId] = []
        to_remove: List[MessageId] = []

        def too_old(ts: int) -> bool:
            return self.get_now_ts() - ts > self.unsorted_ttl

        for msg, ts in self.unsorted_deliveries.items():
            if msg in promise:
                delivered.append(msg)
                to_remove.append(msg)
            elif too_old(ts):
                to_remove.append(msg)
        if delivered:
            LOG.log(TRACE, 'The following messages found matching promise: %s',
                    delivered)
            self.recently_delivered[promise] = delivered

        for m in to_remove:
            del self.unsorted_deliveries[m]
        LOG.log(TRACE, 'unsorted size after grooming: %s',
                len(self.unsorted_deliveries))

    def notify_delivered(self, message_id: MessageId):
        # [KN] This function is expected to be called from Motr.
        with self.lock:
            LOG.debug('received msg id %s, notify waiting clients %s',
                      message_id, self.waiting_clients.items())
            for promise, client in self.waiting_clients.items():
                LOG.debug('waiting promise %s', promise)
                if message_id in promise:
                    LOG.log(TRACE, 'Found a waiting client for %s: %s',
                            message_id, promise)
                    old_list = self.recently_delivered.get(promise, [])
                    old_list.append(message_id)
                    self.recently_delivered[promise] = old_list
                    with client:
                        client.notify()
                    return
            # If notify_delivered() was invoked before wait_for_all(), i.e.
            # if the ha message is already delivered before the sender starts
            # waiting on the same, append the delivered message to the list of
            # unsorted_delivered, so that the delivery is found before
            # wait_for_{all, any}() starts the conditional wait.
            self.unsorted_deliveries[message_id] = self.get_now_ts()

    # This function must be invoked with the self.lock held.
    def check_if_delivered_locked(
            self, promise: HaLinkMessagePromise) -> HaLinkMessagePromise:
        if not self.lock.locked():
            raise RuntimeError('DeliveryHerald.lock not acquired')
        if promise in self.recently_delivered:
            confirmed_msgs = self.recently_delivered.pop(promise)
            LOG.debug('Thread unblocked - %s just received', confirmed_msgs)
            del self.waiting_clients[promise]
            promise.exclude_ids(confirmed_msgs)
        return promise
