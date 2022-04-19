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
from cortx.utils.event_framework.health import HealthAttr, HealthEvent
from hax.ha.event.event import HaEvent


class NodeEvent(HaEvent):
    def __init__(self):
        logging.debug('Inside NodeEvent')

    def create_event(self, node_id, node_name, health_status):
        logging.debug('Inside create_event of NodeEvent')
        self.payload = {
            HealthAttr.SOURCE.value: HEALTH_EVENT_SOURCES.HARE.value,
            HealthAttr.CLUSTER_ID.value: NOT_DEFINED,
            HealthAttr.SITE_ID.value: NOT_DEFINED,
            HealthAttr.RACK_ID.value: NOT_DEFINED,
            HealthAttr.STORAGESET_ID.value: NOT_DEFINED,
            HealthAttr.NODE_ID.value: node_id,
            HealthAttr.RESOURCE_TYPE.value: 'node',
            HealthAttr.RESOURCE_ID.value: node_id,
            HealthAttr.RESOURCE_STATUS.value: health_status,
            HealthAttr.SPECIFIC_INFO.value: {}
            }

        self.event = HealthEvent(**self.payload)

        # 'specific_info' is resource type specific information.
        # For e.g. incase of Node 'generation_id' will be pod name
        self.event.set_specific_info({"generation_id": node_name})
        return self.event.json
