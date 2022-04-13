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
from hax.ha.event.node import NodeEvent
from hax.ha.message_type.message_type import HealthMessage
from hax.types import ObjT, Fid
from hax.util import ConsulUtil
from cortx.utils.conf_store import Conf


class Ha():
    resources = {ObjT.NODE: NodeEvent}
    # currently only online is supported for node status
    message_types = {ObjT.NODE: [HealthMessage]}

    def __init__(self, util: ConsulUtil):
        self.util = util

    def send_event(self,
                   resource_type: ObjT,
                   resource_id: str,
                   resource_name: str,
                   resource_status: str):
        resource = self.resources[resource_type]()
        event = resource.create_event(resource_id,
                                      resource_name,
                                      resource_status)

        interfaces = self.message_types[resource_type]
        for interface in interfaces:
            sender = interface()
            sender.send(event, self.util)

    def check_and_send(self,
                       parent_resource_type: ObjT,
                       fid: Fid,
                       resource_status: str):
        # TODO Need to have generic function to get resource status
        if (self.util.get_local_node_status() == resource_status and
                self.util.is_proc_local(fid)):
            resource = self.util.get_process_node(fid)
            resource_id = str(Conf.machine_id)
            logging.debug('Sending %s event for resource %s',
                          resource_status, resource)
            self.send_event(
                resource_type=parent_resource_type,
                resource_id=resource_id,
                resource_name=resource,
                resource_status=resource_status)
