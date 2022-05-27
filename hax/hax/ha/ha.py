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
from typing import List, NamedTuple, Optional
from hax.ha.event.node import NodeEvent
from hax.ha.message_type.message_type import HealthMessage
from hax.types import HAState, ObjHealth, ObjT, Fid
from hax.util import ConsulUtil
from cortx.utils.conf_store import Conf

LOG = logging.getLogger('hax')


Resource = NamedTuple('Resource', [('type', ObjT), ('id', str),
                                   ('name', str), ('status', str)])

class Ha():
    resources = {ObjT.NODE: NodeEvent}
    # currently only online is supported for node status
    message_types = {ObjT.NODE: [HealthMessage]}

    def __init__(self, util: ConsulUtil):
        self.util = util

    def send_event(self, res: Resource):
        resource = self.resources[res.type]()
        event = resource.create_event(res.id,
                                      res.name,
                                      res.status)

        interfaces = self.message_types[res.type]
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
            LOG.debug('Sending %s event for resource %s',
                      resource_status, resource)
            self.send_event(Resource(type=parent_resource_type,
                                     id=resource_id,
                                     name=resource,
                                     status=resource_status))

    def generate_event_for_process(self,
                                   ha_state: HAState) -> Optional[Resource]:
        cns = self.util
        resource = None
        # TODO handle process 'online' events
        if (ha_state.status == ObjHealth.OFFLINE and
                cns.am_i_rc() or cns.is_proc_local(ha_state.fid)):

            node_name = cns.get_process_node(ha_state.fid)
            node_fid = cns.get_node_fid(node_name)
            state = cns.get_process_based_node_state(node_fid)
            # since the node event is not always for local node
            # when node is offline, rc node sends the offline event.
            resource_id = cns.get_machineid_by_nodename(node_name)

            resource = Resource(type=ObjT.NODE,
                                id=resource_id,
                                name=node_name,
                                status=state)
        return resource

    def broadcast(self, ha_states: List[HAState]) -> None:

        resource_map = {
            ObjT.PROCESS.value: self.generate_event_for_process}

        LOG.debug('Notifying HA with states %s', ha_states)
        for st in ha_states:
            obj_type = st.fid.container
            if obj_type not in resource_map:
                LOG.exception('Events for object type %s is not supported',
                              obj_type)
                continue
            resource = resource_map[obj_type](st)
            if resource:
                LOG.debug('Sending %s event for resource %s:%s',
                          resource.status, resource.type, resource.name)
                try:
                    self.send_event(resource)
                except Exception as e:
                    LOG.warning("Send event failed due to '%s'", e)
