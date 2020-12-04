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
from typing import Dict

from hax.exception import NotDelivered
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
    recently_delivered: Dict[HaLinkMessagePromise, MessageId] = {}
    waiting_clients: Dict[HaLinkMessagePromise, Condition] = {}
    lock = Lock()

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
            LOG.debug('Blocking until %s is confirmed', promise)
            condition.wait(timeout=timeout_sec)
        with self.lock:
            del self.waiting_clients[promise]
            if promise not in self.recently_delivered:
                raise NotDelivered('None of message tags =' + str(promise) +
                                   '  were delivered to Motr within ' +
                                   str(timeout_sec) + ' seconds timeout')
            LOG.debug('Thread unblocked - %s has just been received',
                      self.recently_delivered[promise])
            del self.recently_delivered[promise]

    def wait_for_all(self,
                     promise: HaLinkMessagePromise,
                     timeout_sec: float = 30.0):
        """
        Blocks the current thread until all of the messages in
        promise._ids are reported by Motr as delivered.

        Raises NotDelivered exception when timeout_sec exceeds.
        """
        for msg in promise._ids:
            condition = Condition()
            with self.lock:
                self.waiting_clients[promise] = condition
                LOG.debug('waiting clients %s', self.waiting_clients)

            with condition:
                LOG.debug('Blocking until %s is confirmed', promise)
                condition.wait(timeout=timeout_sec)
            with self.lock:
                if promise not in self.recently_delivered:
                    raise NotDelivered('None of message tags =' +
                                       str(promise) +
                                       '  were delivered to Motr')
                LOG.debug('Thread unblocked - %s just received',
                          self.recently_delivered[promise])

    def notify_delivered(self, message_id: MessageId):
        # [KN] This function is expected to be called from Motr.
        with self.lock:
            LOG.debug('notify waiting clients %s',
                      self.waiting_clients.items())
            for promise, client in self.waiting_clients.items():
                LOG.debug('received msg id %s, waiting promise %s',
                          message_id, promise)
                if message_id in promise:
                    LOG.debug('Found a waiting client for %s: %s', message_id,
                              promise)
                    self.recently_delivered[promise] = message_id
                    with client:
                        client.notify()
                    return
