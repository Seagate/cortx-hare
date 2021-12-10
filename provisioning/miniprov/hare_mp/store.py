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

from typing import Any, List

from cortx.utils.conf_store import Conf

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

    def get_storage_set_nodes(self) -> List[str]:
        raise NotImplementedError()

    def search_val(self, parent_key: str, search_key: str,
                   search_val: str) -> List[str]:
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

    def get_storage_set_nodes(self) -> List[str]:
        storage_set_index = self.get_storage_set_index()

        storage_nodes_key = (f'cluster>storage_set[{storage_set_index}]>nodes')
        storage_nodes = self.get(storage_nodes_key)

        for node in storage_nodes:
            node_type = self.get(f'node>{node}>type')
            # Skipping controller node
            if node_type != 'storage_node':
                storage_nodes.remove(node)

        return storage_nodes

    def search_val(self, parent_key: str, search_key: str,
                   search_val: str) -> List[str]:
        """
        Searches a given key value under the given parent key.
        """
        return self.conf.search(self.index, parent_key, search_key, search_val)


def get_machine_id() -> str:
    machine_id = Conf.machine_id
    if machine_id:
        return machine_id
    raise RuntimeError('Machine-id is not found.')
