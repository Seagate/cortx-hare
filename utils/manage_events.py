# Copyright (c) 2021 Seagate Technology LLC and/or its Affiliates
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License
# for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
# For any questions about this software or licensing, please email
# opensource@seagate.com or cortx-questions@seagate.com.


import logging
import json
from typing import List, Optional
from dataclasses import dataclass

from cortx.utils.message_bus import MessageBus, MessageConsumer
from ha.core.event_manager.event_manager import EventManager
from ha.core.event_manager.subscribe_event import SubscribeEvent

COMPONENT_ID = 'hare'

@dataclass
class Event:
    version: str
    event_type: str
    event_id: str
    resource_type: str
    cluster_id: str
    site_id: str
    rack_id: str
    storageset_id: str
    node_id: str
    resource_id: str
    timestamp: str


class EventListener():

    """
    This is listener for event manager

    Typical use case of this class is as follows
    subscribe(event list) - subscribe to events for listening, returns topic
                            which can be used for listening
    _listen(topic) - reading messages received on above topic
    unsubscribe(event list) - unsubscribe as we dont want to receive these
                              events anymore
    get_message_type() - returns topic just in case user is not maintaining
                         output of 'subscribe'
    Note: 1. There is only 1 topic(message type, queue) for given component.
          2. When component subcribes for event for the 1st time topic is
             created and returned to user.
          3. This topic will be used by user to listen for events.
          4. After event is received in queue, user will read it, process it
             and acknowledge it
    """
    event_manager = None
    consumer = None
    topic = None

    def __init__(self, event_list: List[SubscribeEvent]):
        '''

        We will subscribe to events passes as 'event_list'.
        We will also create consumer for events
        '''
        logging.debug('Inside EventListener')
        self.event_manager = EventManager.get_instance()

        topic = self._subscribe(event_list)
        if topic is None:
           raise RuntimeError('Failed to subscribe to events')

        message_bus = MessageBus()
        self.consumer = MessageConsumer(message_bus=message_bus,
                                        consumer_id=COMPONENT_ID,
                                        consumer_group=COMPONENT_ID,
                                        message_types=[topic],
                                        auto_ack=False,
                                        offset='earliest')

    def _subscribe(self, event_list: List[SubscribeEvent]) -> str:
        logging.info('Subscribing to events: %s', event_list)
        kafka_topic_name = self.event_manager.subscribe(COMPONENT_ID,
                                                        event_list)
        return kafka_topic_name

    def unsubscribe(self, event_list: List[str]) -> bool:
        logging.info('Unsubscribing for events: %s', event_list)
        return self.event_manager.unsubscribe(COMPONENT_ID, event_list)

    def get_next_message(self, time_out) -> Optional[Event]:
        '''
        Listen for events from event manager
        Once user gets message using below command user needs to call ack() to
        acknowledge that message is already processed
        '''
        logging.info('Getting next message from topic: (%s)', self.topic)

        try:
            logging.info('Listening......')
            message = self.consumer.receive(time_out)
            if message is not None:
                return self._parse(message)
            else:
                return None
        except Exception as e:
            logging.error('Exception occured in get_next_message (%s)', e)

    def _parse(self, message: str) -> Event:
        data = json.loads(message.decode('utf-8'))
        return Event(version=data['version'],
                     event_type=data['event_type'],
                     event_id=data['event_id'],
                     resource_type=data['resource_type'],
                     cluster_id=data['cluster_id'],
                     site_id=data['site_id'],
                     rack_id=data['rack_id'],
                     storageset_id=data['storageset_id'],
                     node_id=data['node_id'],
                     resource_id=data['resource_id'],
                     timestamp=data['timestamp'])

    def ack(self):
        '''
        1. This method will commit last read message offset for confirming
           which messages the consumer has already processed
        2. Consumer will read message using 'listen' and will acknowledge
           that message using ack method
        '''
        self.consumer.ack()
