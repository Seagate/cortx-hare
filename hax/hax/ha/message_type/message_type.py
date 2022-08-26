# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
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
from hax.util import ConsulUtil
from hax.ha.message_interface.message_interface import MessageBusInterface


class MessageType():
    def __init__(self):
        """Message base class with abstract send method."""
        logging.debug('Inside MessageType')

    def send(self, event, util: ConsulUtil):
        raise NotImplementedError()


class HealthMessage(MessageType):
    topic_list = {'cortx_health_events': MessageBusInterface}

    def __init__(self):
        logging.debug('Inside HealthMessage')

    def send(self, event, util: ConsulUtil):
        logging.info('Sending HealthMessage: %s', event)
        for interface in self.topic_list.items():
            sender = interface[1](util)
            message_type = interface[0]
            sender.create_producer(message_type)
            sender.send(event)
