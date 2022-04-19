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

from cortx.utils.conf_store import Conf
from typing import List, Dict, Any
from cortx.utils.cortx import Const
from hare_mp.types import MissingKeyError


class ValueProvider:
    def __init__(self):
        self.url = None

    def get(self, key: str, allow_null: bool = False) -> Any:
        ret = self._raw_get(key)
        if ret is None and not allow_null:
            raise MissingKeyError(key, self.url)
        return ret

    def _raw_get(self, key: str) -> str:
        raise NotImplementedError()

    def get_cluster_id(self) -> str:
        raise NotImplementedError()

    def get_machine_id(self) -> str:
        raise NotImplementedError()

    def get_storage_set_index(self) -> int:
        raise NotImplementedError()

    def get_machine_ids_for_service(self, service_type: str) -> List[str]:
        raise NotImplementedError()

    def get_machine_ids_for_component(self, comp_type: str) -> List[str]:
        raise NotImplementedError()

    def get_hostnames_for_service(self, service_type: str) -> List[str]:
        raise NotImplementedError()

    def get_data_nodes(self) -> List[str]:
        raise NotImplementedError()

    def search_val(self, parent_key: str, search_key: str,
                   search_val: str) -> List[str]:
        raise NotImplementedError()

    def get_motr_clients(self) -> List[Dict[str, Any]]:
        raise NotImplementedError()


class ConfStoreProvider(ValueProvider):
    def __init__(self, url: str, index='hare'):
        self.url = url
        # Note that we don't instantiate Conf class on purpose.
        #
        # Conf is a 'singleton' (as it is understood by its authors).
        # In fact it is a class with static methods only.
        #
        # fail_reload flag is required to be False otherwise the error as
        # follows will be thrown when ConfStoreProvider is instantiated not for
        # the first time in the current address space:
        #
        # ConfError: error(22): conf index hare already exists
        #
        # Reason: although Conf has static methods only, it does have a state.
        # That state is also static...

        conf = Conf
        conf.load(index, url, fail_reload=False)
        self.conf = conf
        self.index = index

    def _raw_get(self, key: str) -> str:
        return self.conf.get(self.index, key)

    def get_machine_ids_for_service(self, service_type: str) -> List[str]:
        """
        Return a list of pod's machine_id w.r.t service_type.
        service_type will be like Const.SERVICE_MOTR_IO.value,
        Const.SERVICE_S3_SERVER.value etc
        """
        return self.get_machine_ids_for_attribute('services', service_type)

    def get_hostnames_for_service(self, service_type: str) -> List[str]:
        """
        Return a list of pod's hostname w.r.t service_type.
        service_type will be like Const.SERVICE_MOTR_IO.value,
        Const.SERVICE_S3_SERVER.value etc
        """
        nodes: List[str] = []
        machines = self.get_machine_ids_for_service(service_type)
        for machine_id in machines:
            nodes.append(self.get(f'node>{machine_id}>hostname'))
        return nodes

    def get_machine_ids_for_component(self, comp_type: str) -> List[str]:
        """
        Return a list of pod's machine_id w.r.t component type.
        component type will be like Const.COMPONENT_MOTR.value,
        Const.COMPONENT_CCLIENT.value etc
        """
        return self.get_machine_ids_for_attribute('name', comp_type)

    def get_machine_ids_for_attribute(self, attr_type: str,
                                      name: str) -> List[str]:
        """
        Return a list of pod's machine_id for the machines consisting
        the attribute name under the given attribute type.
        attribute type can be like service, node, etc.
        """
        nodes: List[str] = []
        machines: Dict[str, Any] = self.get('node')
        # example ouput for search_val()
        # attr_type = services
        # ['node>32bdeac034fe4155af4ca66951d410e9>components[1]>services[0]']
        values = self.search_val('node', attr_type, name)

        for machine_id in machines.keys():
            result = [val for val in values if machine_id in val]
            if result:
                nodes.append(machine_id)
        return nodes

    def get_cluster_id(self) -> str:
        machine_id = self.get_machine_id()
        cluster_id = self.get(f'node>{machine_id}>cluster_id')
        return cluster_id

    def get_machine_id(self) -> str:
        return get_machine_id()

    def get_storage_set_index(self) -> int:
        i = 0
        machine_id = self.get_machine_id()
        storage_set_id = self.get((f'node>{machine_id}>'
                                   f'storage_set'))

        for storage_set in self.get('cluster>storage_set'):
            if storage_set['name'] == storage_set_id:
                return i
            i += 1

        raise RuntimeError('No storage set found. Is ConfStore data valid?')

    def get_data_nodes(self) -> List[str]:
        return self.get_machine_ids_for_service(Const.SERVICE_MOTR_IO.value)

    def search_val(self, parent_key: str, search_key: str,
                   search_val: str) -> List[str]:
        """
        Searches a given key value under the given parent key.
        """
        return self.conf.search(self.index, parent_key, search_key, search_val)

    def get_motr_clients(self) -> List[Dict[str, Any]]:
        """
        Returns a list of all motr clients with their name and instances.
        Example
        clients:
        -   name: rgw
            num_instances: 1
        -   name: other
            num_instances: 2
        """
        clients = self.get('cortx>motr>clients', allow_null=True)
        if clients is None:
            return []
        for client in clients:
            instances = int(str(client.get('num_instances')))
            if instances == 0:
                clients.remove(client)
        return clients


def get_machine_id() -> str:
    machine_id = Conf.machine_id
    if machine_id:
        return machine_id
    raise RuntimeError('Machine-id is not found.')
