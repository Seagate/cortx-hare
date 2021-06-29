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

from typing import Any

from cortx.utils.conf_store import Conf

from hare_mp.types import MissingKeyError


class ValueProvider:
    def get(self, key: str, allow_null: bool = False) -> Any:
        ret = self._raw_get(key)
        if ret is None and not allow_null:
            raise MissingKeyError(key)
        return ret

    def _raw_get(self, key: str) -> str:
        raise NotImplementedError()

    def get_machine_id(self) -> str:
        raise NotImplementedError()

    def get_cluster_id(self) -> str:
        raise NotImplementedError()

    def get_storage_set_id(self) -> int:
        raise NotImplementedError()


class ConfStoreProvider(ValueProvider):
    def __init__(self, url: str):
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
        conf.load('hare', url, fail_reload=False)
        self.conf = conf

    def _raw_get(self, key: str) -> str:
        return self.conf.get('hare', key)

    def get_machine_id(self) -> str:
        with open('/etc/machine-id', 'r') as f:
            machine_id = f.readline().strip('\n')
            return machine_id

    def get_cluster_id(self) -> str:
        machine_id = self.get_machine_id()
        cluster_id = self.get(f'server_node>{machine_id}>cluster_id')
        return cluster_id

    def get_storage_set_id(self) -> int:
        machine_id = self.get_machine_id()
        storage_set_id = self.get((f'server_node>{machine_id}>'
                                   f'storage_set_id'))
        return int(storage_set_id)

    def get_hostname(self) -> str:
        machine_id = self.get_machine_id()
        hostname = self._raw_get(f'server_node>{machine_id}>hostname')
        return hostname
