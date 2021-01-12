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
from threading import Condition, Lock
from typing import Dict, List

from hax.exception import NotDelivered
from hax.log import TRACE
from hax.types import HaLinkMessagePromise, MessageId

LOG = logging.getLogger('hax')


class DeliveryHerald:
    """
    Thread synchronizing block that implements the following use case:
    - Some message is sent from Python land to Motr
    - And the Python code needs to wait until a delivery is confirmed by Motr.

    Typical usage is as follows (assuming that delivery_herald is a singleton):

        tag_list = ffi.ha_broadcast(_ha_ctx, make_array(HaNoteStruct, notes),
                                    len(notes))
        delivery_herald.wait_for_any(HaLinkMessagePromise(tag_list))
        # if we are here then the delivery was confirmed
    """
    def __init__(self):
        self.recently_delivered: Dict[HaLinkMessagePromise,
                                      List[MessageId]] = {}
        self.waiting_clients: Dict[HaLinkMessagePromise, Condition] = {}
        self.lock = Lock()

    def _verify_delivered(self,
                          promise: HaLinkMessagePromise,
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
        LOG.log(TRACE, 'Thread unblocked - %s just received',
                confirmed_msgs)
        promise.exclude_ids(confirmed_msgs)

    def wait_for_any(self,
                     promise: HaLinkMessagePromise,
                     timeout_sec: float = 30.0):
        """
        Blocks the current thread until at least one of the messages in
        promise._ids are reported by Motr as delivered.

        Raises NotDelivered exception when timeout_sec exceeds.
        """
        condition = Condition()
        with self.lock:
            self.waiting_clients[promise] = condition

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
        with self.lock:
            self.waiting_clients[promise] = condition
            LOG.log(TRACE, 'waiting clients %s', self.waiting_clients)

        while not promise.is_empty():
            with condition:
                LOG.log(TRACE, 'Blocking until %s is confirmed', promise)
                condition.wait(timeout=timeout_sec)
            with self.lock:
                self._verify_delivered(promise, timeout_sec)
                if not promise.is_empty():
                    self.waiting_clients[promise] = condition

    def notify_delivered(self, message_id: MessageId):
        # [KN] This function is expected to be called from Motr.
        with self.lock:
            LOG.log(TRACE, 'notify waiting clients %s',
                    self.waiting_clients.items())
            for promise, client in self.waiting_clients.items():
                LOG.log(TRACE, 'received msg id %s, waiting promise %s',
                        message_id, promise)
                if message_id in promise:
                    LOG.log(TRACE, 'Found a waiting client for %s: %s',
                            message_id, promise)
                    old_list = self.recently_delivered.get(promise, [])
                    old_list.append(message_id)
                    self.recently_delivered[promise] = old_list
                    with client:
                        client.notify()
                    return
