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
from hax.types import HAState, ObjHealth, ObjT, Fid
from hax.ha.resource.node import Node
from hax.ha.resource.resource import ResourceType
from hax.ha.event.event import HaEvent
from hax.configmanager import ConfigManager
from cortx.utils.conf_store import Conf

LOG = logging.getLogger('hax')


Resource = NamedTuple('Resource', [('type', ResourceType), ('id', str),
                                   ('name', str), ('status', str)])


class Ha():
    def __init__(self, util: ConfigManager):
        self.util = util

    def send_event(self, res: Resource):
        event: HaEvent = res.type.create_event(res.id,
                                               res.name,
                                               res.status)

        event.send(self.util)

    def check_and_send(self,
                       parent_resource_type: ObjT,
                       fid: Fid,
                       resource_status: str):
        resources = {ObjT.NODE: Node}

        # TODO Need to have generic function to get resource status
        logging.debug('Inside check_and_send')
        if (self.util.get_local_node_status() == resource_status and
                self.util.is_proc_local(fid)):
            resource_name = self.util.get_process_node(fid)
            resource_id = str(Conf.machine_id)
            LOG.debug('Sending %s event for resource %s',
                      resource_status, resource_name)
            self.send_event(Resource(type=resources[parent_resource_type](),
                                     id=resource_id,
                                     name=resource_name,
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
            # silence mypy
            assert node_fid is not None
            state = cns.get_process_based_node_state(node_fid)
            LOG.debug('received node state=%s node=%s', state, node_name)
            # since the node event is not always for local node
            # when node is offline, rc node sends the offline event.
            resource_id = cns.get_machineid_by_nodename(node_name)
            if resource_id:
                resource = Resource(type=Node(),
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
