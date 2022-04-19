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

import json
import logging
from typing import Optional
from dataclasses import dataclass
from hax.util import ConsulUtil
from cortx.utils.message_bus import MessageBus
from cortx.utils.message_bus import (MessageConsumer, MessageProducer,
                                     MessageBusAdmin)
from cortx.utils.conf_store import Conf
from hax.ha.const import HEALTH_EVENT_SOURCES, EVENT_MANAGER_KEYS
from hax.ha.event.event import HaEvent

COMPONENT_ID = 'hare'
ADMIN_ID = "hare_admin"


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


class MessageInterface():
    def __init__(self):
        logging.debug('Inside MessageInterface')

    def get_next_message(self, time_out) -> Optional[Event]:
        raise NotImplementedError()

    def ack(self):
        raise NotImplementedError()


class MessageBusInterface(MessageInterface):
    def __init__(self, util: ConsulUtil):
        logging.debug('Inside  MessageBusInterface')
        self.initialize_bus(util)

    def create_producer(self, message_type):
        self._register_message_type(message_type)

        self.producer = MessageProducer(
                            producer_id=str(HEALTH_EVENT_SOURCES.HARE),
                            message_type=message_type)
        return self.producer

    def initialize_bus(self, util: ConsulUtil):
        """
        This creates a MessageBus internal global in-memory object which is
        indirectly part of the process address space. Thus
        `MessageBus.init()` must be invoked within process's address space.
        """
        configpath = util.get_configpath(allow_null=True)
        if configpath:
            Conf.load('cortx_conf', configpath, skip_reload=True)

            message_server_endpoints = Conf.get(
                            'cortx_conf',
                            'cortx>external>kafka>endpoints')
            MessageBus.init(message_server_endpoints)
        else:
            logging.warning('initialize_bus skipped as configpath not found')
            raise Exception('initialize_bus skipped as configpath not found')

    def send(self, event: HaEvent):
        event_to_send = json.dumps(event)
        self.producer.send([event_to_send])

    def _register_message_type(self, message_type,
                               partitions: int = 1):
        admin = MessageBusAdmin(admin_id=ADMIN_ID)
        try:
            if message_type not in admin.list_message_types():
                admin.register_message_type(message_types=[message_type],
                                            partitions=partitions)
        except Exception as e:
            if "TOPIC_ALREADY_EXISTS" not in str(e):
                raise(e)

    def create_listener(self, group_id: str = COMPONENT_ID):
        logging.debug('Inside EventListener')

        topic = self._subscribe()
        if topic is None:
            raise RuntimeError('Failed to subscribe to events')

        self.consumer = MessageConsumer(
            consumer_id=COMPONENT_ID,
            consumer_group=group_id,
            message_types=[topic],
            auto_ack=str(False),
            offset='earliest')

    def _subscribe(self) -> str:
        # TODO create a PR for cortx-ha. The type annotation seems to be wrong

        # HA functionality won't work in containers. Hare is the only
        # subscriber to HA's event manager, and the topic name is hardcoded,
        # in HA code. So, topic prefix is imported which is in format
        # 'ha_event_<component_id>'
        ha_topic_prefix = str(EVENT_MANAGER_KEYS.MESSAGE_TYPE_VALUE.value)
        topic = ha_topic_prefix.replace("<component_id>", COMPONENT_ID)
        return topic

    def get_next_message(self, time_out) -> Optional[Event]:
        """
        Listen for events from event manager
        Once user gets message using below command user needs to call ack() to
        acknowledge that message is already processed
        """
        logging.debug('Listening......')
        try:
            # HA container may come up later than hax container, and then
            # register the topic online. We need to wait for it to be
            # available.
            message = self.consumer.receive(time_out)
        except Exception:
            logging.warning('Subscribed topic not available. Waiting...')
            return None
        # FIXME: it seems like receive() returns bytes, not str
        # ..while it is annotated as returning 'list'. Funny.
        if message is not None:
            # msg = str(message)  # wrong type annotation?
            return self._parse(message)
        else:
            return None

    # 'message' returned by receive() is suppose to be of type str but it is
    # bytes. Looks like there is a bug in type information provided by
    # cortx-py-utils. So skipping type information for 'message' for now.
    # See 'get_next_message' for more information
    def _parse(self, message) -> Event:
        data = json.loads(message.decode('utf-8'))
        payload = data['payload']
        header = data['header']
        return Event(version=header['version'],
                     event_type='NOT_DEFINED',
                     event_id=header['event_id'],
                     resource_type=payload['resource_type'],
                     cluster_id=payload['cluster_id'],
                     site_id=payload['site_id'],
                     rack_id=payload['rack_id'],
                     storageset_id=payload['storageset_id'],
                     node_id=payload['node_id'],
                     resource_id=payload['resource_id'],
                     timestamp=header['timestamp'])

    def ack(self):
        """
        1. This method will commit last read message offset for confirming
           which messages the consumer has already processed
        2. Consumer will read message using 'listen' and will acknowledge
           that message using ack method
        """
        self.consumer.ack()
