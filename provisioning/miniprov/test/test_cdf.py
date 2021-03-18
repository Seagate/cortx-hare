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

# Setup utility for Hare to configure Hare related settings, e.g. logrotate,
# report unsupported features, etc.

# flake8: noqa
#
import os
import tempfile
import unittest
from typing import Any
from unittest.mock import MagicMock, Mock

import pkg_resources
from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider, ValueProvider
from hare_mp.types import (DisksDesc, DList, M0Clients, M0ServerDesc, Maybe,
                           NodeDesc, PoolDesc, DiskRef, Protocol, Text)


class TestTypes(unittest.TestCase):
    def test_m0clients(self):
        val = M0Clients(s3=5, other=1)
        self.assertEqual('{ s3 = 5, other = 1 }', str(val))

    def test_protocol(self):
        self.assertEqual('P.tcp', str(Protocol.tcp))
        self.assertEqual('P.o2ib', str(Protocol.o2ib))

    def test_maybe_none(self):
        val = Maybe(None, 'P')
        self.assertEqual('None P', str(val))
        self.assertEqual('Some (P.tcp)', str(Maybe(Protocol.tcp, 'P')))

    def test_disks_empty(self):
        val = M0ServerDesc(runs_confd=Maybe(True, 'Bool'),
                           io_disks=DisksDesc(meta_data=Maybe(None, 'Text'),
                                              data=DList([], 'List Text')))
        self.assertEqual(
            '{ runs_confd = Some (True), io_disks = { meta_data = None Text, data = [] : List Text } }',
            str(val))

    def test_pooldesc_empty(self):
        val = PoolDesc(
            name=Text('storage_set_name'),
            disk_refs=Maybe(DList([], 'List DiskRef'), []),
            data_units=0,
            parity_units=0)
        self.assertEqual(
            '{ name = "storage_set_name", disk_refs = Some ([] : List DiskRef), data_units = 0, parity_units = 0 }',
            str(val))

    def test_m0server_with_disks(self):
        val = M0ServerDesc(
            runs_confd=Maybe(True, 'Bool'),
            io_disks=DisksDesc(
                meta_data=Maybe(None, 'Text'),
                data=DList([Text('/disk1'), Text('/disk2')], 'test')))
        self.assertEqual(
            '{ runs_confd = Some (True), io_disks = { meta_data = None Text, data = ["/disk1", "/disk2"] } }',
            str(val))


class TestCDF(unittest.TestCase):
    def _get_confstore_template(self) -> str:
        resource_path = 'templates/hare.config.conf.tmpl.json'
        raw_content: bytes = pkg_resources.resource_string(
            'hare_mp', resource_path)
        return raw_content.decode('utf-8')

    def test_template_sane(self):
        _, path = tempfile.mkstemp()
        try:
            with open(path, 'w') as f:
                f.write(self._get_confstore_template())
            store = ConfStoreProvider(f'json://{path}')
            #
            # the method will raise an exception if either
            # Dhall is unhappy or some values are not found in ConfStore
            CdfGenerator(provider=store).generate()
        finally:
            os.unlink(path)

    def test_it_works(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1"
                },
                'cluster>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'cluster>srvnode_1>hostname':
                'myhost',
                'cluster>srvnode_1>network>data>interface_type':
                'tcp',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cluster>srvnode_1>storage>metadata_devices': ['/dev/meta'],
                'cluster>srvnode_1>s3_instances':
                1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>site>storage_set_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set>server_node_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>name': 'StorageSet-1',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>server_nodes': ['srvnode_1'],
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>data': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>parity': 0,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>spare': 0,
                'server_node>0e79f22f24c54f15a2ae94fc1769d271>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node>0e79f22f24c54f15a2ae94fc1769d272>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node':{'0e79f22f24c54f15a2ae94fc1769d271': {'cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695'}}
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        CdfGenerator(provider=store).generate()

    def test_provided_values_respected(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1"
                },
                'cluster>srvnode_1>hostname':
                'myhost',
                'cluster>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cluster>srvnode_1>storage>metadata_devices': ['/dev/meta'],
                'cluster>srvnode_1>s3_instances':
                1,
                'cluster>srvnode_1>network>data>interface_type':
                'o2ib',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>site>storage_set_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set>server_node_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>name': 'StorageSet-1',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>server_nodes': ['srvnode_1'],
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>data': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>parity': 0,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>spare': 0,
                'server_node>0e79f22f24c54f15a2ae94fc1769d271>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node>0e79f22f24c54f15a2ae94fc1769d272>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node':{'0e79f22f24c54f15a2ae94fc1769d271': {'cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695'}}
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('myhost'), ret[0].hostname)
        self.assertEqual(Text('eth1'), ret[0].data_iface)
        self.assertEqual(1, ret[0].s3_instances)

        ret = CdfGenerator(provider=store)._create_pool_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('StorageSet-1'), ret[0].name)
        self.assertEqual(1, ret[0].data_units)
        self.assertEqual(0, ret[0].parity_units)
        disk_refs = ret[0].disk_refs.value
        self.assertEqual(Text('srvnode_1'), disk_refs.value[0].node.value)
        self.assertEqual(Text('/dev/sdb'), disk_refs.value[0].path)

        ret = CdfGenerator(provider=store)._create_profile_descriptions(ret)
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('Profile_the_pool'), ret[0].name)
        self.assertEqual(1, len(ret[0].pools.value))
        self.assertEqual(Text('StorageSet-1'), ret[0].pools.value[0])

    def test_disk_refs_can_be_empty(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1"
                },
                'cluster>srvnode_1>hostname':
                'myhost',
                'cluster>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'cluster>srvnode_1>storage>data_devices': [],
                'cluster>srvnode_1>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cluster>srvnode_1>storage>metadata_devices': ['/dev/meta'],
                'cluster>srvnode_1>s3_instances':
                1,
                'cluster>srvnode_1>network>data>interface_type':
                'o2ib',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>site>storage_set_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set>server_node_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>name': 'StorageSet-1',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>server_nodes': ['srvnode_1'],
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>data': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>parity': 0,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>spare': 0,
                'server_node>0e79f22f24c54f15a2ae94fc1769d271>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node>0e79f22f24c54f15a2ae94fc1769d272>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node':{'0e79f22f24c54f15a2ae94fc1769d271': {'cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695'}}
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)
        ret = CdfGenerator(provider=store).generate()


    def test_invalid_storage_set_configuration_rejected(self):
        ''' This test case checks whether exception will be raise if total
            number of data devices are less than
            data_units + parity_units + spare_units
        '''
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1"
                },
                'cluster>srvnode_1>hostname':
                'myhost',
                'cluster>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cluster>srvnode_1>storage>metadata_devices': ['/dev/meta'],
                'cluster>srvnode_1>s3_instances':
                1,
                'cluster>srvnode_1>network>data>interface_type':
                'o2ib',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>site>storage_set_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set>server_node_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>name': 'StorageSet-1',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>server_nodes': ['srvnode_1'],
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>data': 2,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>parity': 0,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>spare': 0,
                'server_node>0e79f22f24c54f15a2ae94fc1769d271>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node>0e79f22f24c54f15a2ae94fc1769d272>cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695',
                'server_node':{'0e79f22f24c54f15a2ae94fc1769d271': {'cluster_id': '92f444df-87cc-4137-b680-aab3b35d1695'}}
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        with self.assertRaises(RuntimeError) as e:
            CdfGenerator(provider=store)._create_pool_descriptions()

        the_exception = e.exception
        self.assertEqual('Invalid storage set configuration', str(the_exception))

    def test_metadata_is_hardcoded(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1"
                },
                'cluster>srvnode_1>hostname':
                'myhost',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cluster>srvnode_1>s3_instances':
                1,
                'cluster>srvnode_1>network>data>interface_type':
                'o2ib',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>site>storage_set_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set>server_node_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>name': 'StorageSet-1',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>server_nodes': ['srvnode_1'],
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>data': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>parity': 0
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('/dev/vg_metadata_srvnode-1/lv_raw_metadata'),
                         ret[0].meta_data)

    def test_multiple_nodes_supported(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1",
                    "zweite": "srvnode_2"
                },
                'cluster>srvnode_1>hostname': 'myhost',
                'cluster>srvnode_1>network>data>private_interfaces': ['eth1'],
                'cluster>srvnode_1>network>data>interface_type': 'o2ib',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_2>hostname': 'host-2',
                'cluster>srvnode_2>network>data>private_interfaces': ['eno1'],
                'cluster>srvnode_2>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>storage>metadata_devices': ['/dev/meta'],
                'cluster>srvnode_1>s3_instances': 1,
                'cluster>srvnode_2>hostname': 'host-2',
                'cluster>srvnode_2>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_2>storage>metadata_devices': ['/dev/meta'],
                'cluster>srvnode_2>s3_instances': 5,
                'cluster>srvnode_2>network>data>interface_type': 'tcp',
                'cluster>srvnode_2>storage>data_devices': ['/dev/sdb'],
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>site>storage_set_count': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set>server_node_count': 2,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>name': 'StorageSet-1',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>server_nodes': ['srvnode_1', 'srvnode_2'],
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>data': 1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set1>durability>parity': 0
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(2, len(ret))
        self.assertEqual(Text('myhost'), ret[0].hostname)
        self.assertEqual(Text('eth1'), ret[0].data_iface)
        self.assertEqual(1, ret[0].s3_instances)
        self.assertEqual(Text('host-2'), ret[1].hostname)
        self.assertEqual(Text('eno1'), ret[1].data_iface)
        self.assertEqual(5, ret[1].s3_instances)
        self.assertEqual('Some (P.o2ib)', str(ret[0].data_iface_type))
        self.assertEqual('Some (P.tcp)', str(ret[1].data_iface_type))

    def test_iface_type_can_be_null(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1"
                },
                'cluster>srvnode_1>hostname':
                'myhost',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>network>data>interface_type':
                None,
                'cluster>srvnode_1>s3_instances':
                1,
                'cluster>srvnode_1>network>data>private_interfaces':
                ['eth1', 'eno2']
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertEqual('None P', str(ret[0].data_iface_type))
