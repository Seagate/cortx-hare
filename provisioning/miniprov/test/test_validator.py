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

# flake8: noqa
import unittest
import json
import socket

from hare_mp.store import ConfStoreProvider
from hare_mp.validator import Validator


URL = "json:///tmp/test-conf-store.json"

conf_store_data = {
  "provisioner": {
    "cluster_info": {
      "pillar_dir": "/opt/seagate/cortx/provisioner/pillar/groups/all/",
      "num_of_nodes": 1
    },
    "cluster": {
      "num_of_nodes": "1"
    }
  },
  "storage": {
  },
  "system": {
  },
  "node": {
    "srvmachine-1": {
      "name": "srvnode-1",
      "hostname": "ssc-vm-1623.colo.seagate.com",
      "cluster_id": "e766bd52-c19c-45b6-9c91-663fd8203c2e",
      "storage_set_id": 0
    }
  },
  "cluster": {
      "name": "cortx-cluster",
      "storage_set": [
          { "name": "StorageSet-1",
           "nodes": [ "srvmachine-1" ]
          }
       ],
    "storage_sets": {
      "storage-set-1": [
        "srvnode-1"
      ]
    },
    "server_nodes": {
      "7c4fd75dfedd7662e6a39b0a53274922": "srvnode-1"
    },
    "cluster_id": "e766bd52-c19c-45b6-9c91-663fd8203c2e",
    "srvnode-1": {
      "storage_set_id": 0,
      "hostname": "ssc-vm-1623.colo.seagate.com",
      "node_type": "VM",
      "roles": [
        "primary",
        "openldap_server",
        "kafka_server"
      ],
      "is_primary": "true",
      "bmc": {
      },
      "network": {
        "mgmt": {
          "interfaces": [
            "eth0"
          ],
        },
        "data": {
          "public_interfaces": [
            "eth0"
          ],
          "private_interfaces": [
            "eth0"
          ],
          "transport_type": "lnet",
          "private_ip": "",
          "roaming_ip": "127.0.0.1"
        }
      },
      "storage": {
        "enclosure_id": "enclosure-1",
        "metadata_devices": [
          "/dev/sdb"
        ],
        "data_devices": [
          "/dev/sdd",
          "/dev/sde",
          "/dev/sdf",
          "/dev/sdg"
        ]
      },
      "s3_instances": 1
    }
  }}


def update_machine(machine_id: str, hostname: str):
    with open ("/tmp/test-conf-store.json", "w+") as conf_store:
        json.dump(conf_store_data, conf_store)

    with open("/tmp/test-conf-store.json", "r+") as jf:
        data = json.load(jf)
        new_machine = {"node": {
                                       f'{machine_id}': {
                                         "name": "srvnode-1",
                                         "hostname": f'{hostname}',
                                         "cluster_id": "e766bd52-c19c-45b6-9c91-663fd8203c2e",
                                         "storage_set_id": 0
                                       }
                                      }
                      }
        data.update(new_machine)
        data['cluster']['storage_set'][0]['nodes'] = [f'{machine_id}']
        with open("/tmp/temp-test-conf-store.json", "w+") as ujf:
            json.dump(data, ujf)

class TestValidator(unittest.TestCase):
    def test_is_cluster_first_node(self):
        conf = ConfStoreProvider(URL)
        hostname = socket.gethostname()
        machine_id = conf.get_machine_id()
        update_machine(machine_id, hostname)
        validator = Validator(
                        ConfStoreProvider("json:///tmp/temp-test-conf-store.json"))
        self.assertEqual(True, validator.is_first_node_in_cluster())

    def test_invalid_machine_id(self):
        conf = ConfStoreProvider(URL)
        hostname = 'invalid-hostname'
        machine_id = conf.get_machine_id()
        update_machine(machine_id, hostname)
        validator = Validator(
                        ConfStoreProvider("json:///tmp/temp-test-conf-store.json"))
        with self.assertRaises(RuntimeError):
            validator._get_machine_id()
