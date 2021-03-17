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

# Setup utility for Hare to configure Hare related settings, e.g. logrotate,
# report unsupported features, etc.

import socket
from hare_mp.store import ValueProvider


class Validator:
    def __init__(self, provider: ValueProvider):
        super().__init__()
        self.provider = provider

    def _get_machine_id(self) -> str:
        machine_id = self.provider.get_machine_id()
        if not self.is_local_machine_id_valid(machine_id):
            raise RuntimeError(f'invalid machine id {machine_id}')
        return machine_id

    def is_first_node_in_storage_set(self) -> bool:
        machine_id = self._get_machine_id()
        cluster_id = self.provider.get_cluster_id()
        storage_set_id = self.provider.get_storage_set_id()
        server_nodes_key: str = (f'cluster>{cluster_id}>'
                                 f'storage_set[{storage_set_id}]>server_nodes')
        server_nodes = self.provider.get(server_nodes_key)
        return server_nodes[0] == machine_id

    def is_first_node_in_cluster(self) -> bool:
        machine_id = self._get_machine_id()
        cluster_id = self.provider.get_cluster_id()
        server_nodes_key: str = (f'cluster>{cluster_id}>'
                                 f'storage_set[0]>server_nodes')
        server_nodes = self.provider.get(server_nodes_key)
        return server_nodes[0] == machine_id

    def is_local_machine_id_valid(self, machine_id: str) -> bool:
        hostname = self.provider.get(f'server_node>{machine_id}>hostname')
        return hostname == socket.gethostname()
