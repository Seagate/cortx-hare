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
from hax.ha.event.event import HaEvent
from hax.ha.types import InterfaceMapping


class NodeEvent(HaEvent):
    def send(self, util):
        logging.debug('Inside NodeEvent:send')

        subscribers = self.get_subscribers(util, 'node')

        for interface in subscribers:
            sender = InterfaceMapping[interface]()
            sender.send(self.event.json, util)
