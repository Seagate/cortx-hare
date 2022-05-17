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
from hax.ha.const import HEALTH_EVENT_SOURCES, NOT_DEFINED
from hax.ha.event.event import HaEvent
from hax.ha.event.node import NodeEvent
from hax.ha.resource.resource import ResourceType


class Node(ResourceType):
    def create_event(self, resource_id,
                     resource_name, resource_status) -> HaEvent:
        logging.debug('Inside Node:create_event')
        event: NodeEvent = NodeEvent(source=HEALTH_EVENT_SOURCES.HARE.value,
                                     cluster_id=NOT_DEFINED,
                                     site_id=NOT_DEFINED,
                                     rack_id=NOT_DEFINED,
                                     storageset_id=NOT_DEFINED,
                                     node_id=resource_id,
                                     resource_type='node',
                                     resource_id=resource_id,
                                     resource_status=resource_status,
                                     specific_info={"generation_id":
                                                    resource_name})

        return event
