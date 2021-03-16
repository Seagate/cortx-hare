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
from unittest.mock import Mock

import pkg_resources

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider, ValueProvider
from hare_mp.types import (DisksDesc, DList, M0Clients, M0ServerDesc, Maybe,
                           MissingKeyError, PoolDesc, PoolType, Protocol, Text)


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
        val = PoolDesc(name=Text('storage_set_name'),
                       disk_refs=Maybe(DList([], 'List DiskRef'), []),
                       data_units=0,
                       parity_units=0,
                       spare_units=Maybe(0, 'Natural'),
                       type=PoolType.sns)
        self.assertEqual(
            '{ name = "storage_set_name", disk_refs = Some ([] : List DiskRef), '
            'data_units = 0, parity_units = 0, spare_units = Some (0), type = T.PoolType.sns }',
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
        resource_path = 'templates/hare.config.conf.tmpl.3-node.sample'
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
                'cluster>cluster_id':
                'CLUSTER_ID',
                'server_node>MACH_ID>name': 'myhost',
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>network>data>interface_type':
                'tcp',
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'server_node>MACH_ID>storage>cvg':
                [{'data_devices': ['/dev/sdb'], 'metadata_devices': ['/dev/meta']}],
                'server_node>MACH_ID>storage>cvg[0]>metadata_devices':
                ['/dev/meta'],
                'server_node>MACH_ID>s3_instances':
                1,
                'cluster>CLUSTER_ID>site>storage_set_count':
                1,
                'cluster>CLUSTER_ID>storage_set>server_node_count':
                1,
                'cluster>CLUSTER_ID>storage_set[0]>name':
                'StorageSet-1',
                'cluster>CLUSTER_ID>storage_set[0]>server_nodes': ['MACH_ID'],
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns': {'stub': 1},
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>data': 1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>spare': 0,
                'server_node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'server_node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                }
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)

        CdfGenerator(provider=store).generate()

    def test_provided_values_respected(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>CLUSTER_ID>site>storage_set_count': 1,
                'cluster>CLUSTER_ID>storage_set>server_node_count':
                1,
                'cluster>CLUSTER_ID>storage_set[0]>name': 'StorageSet-1',
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns': {'a': 42},
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>data': 1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>spare': 0,
                'cluster>CLUSTER_ID>storage_set[0]>server_nodes': ['MACH_ID'],
                'cluster>CLUSTER_ID>storage_set>server_node_count': 1,
                'cluster>cluster_id': 'CLUSTER_ID',
                'server_node': {'MACH_ID': {'cluster_id': 'CLUSTER_ID'}},
                'server_node>MACH_ID>cluster_id': 'CLUSTER_ID',
                'server_node>MACH_ID>storage>cvg':
                [{'data_devices': ['/dev/sdb'], 'metadata_devices': ['/dev/meta']}],
                'server_node>MACH_ID>storage>cvg[0]>data_devices': ['/dev/sdb'],
                'server_node>MACH_ID>storage>cvg[0]>metadata_devices': ['/dev/meta'],
                'server_node>MACH_ID>hostname':                'myhost',
                'server_node>MACH_ID>name': 'mynodename',
                'server_node>MACH_ID>network>data>interface_type':                'o2ib',
                'server_node>MACH_ID>network>data>private_interfaces':                ['eth1', 'eno2'],
                'server_node>MACH_ID>s3_instances':                1,
            }
            return data.get(value)

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
        self.assertEqual(Text('StorageSet-1__sns'), ret[0].name)
        self.assertEqual(PoolType.sns, ret[0].type)
        self.assertEqual(1, ret[0].data_units)
        self.assertEqual(0, ret[0].parity_units)
        self.assertEqual(0, ret[0].spare_units.get())
        disk_refs = ret[0].disk_refs.value
        self.assertEqual(Text('myhost'), disk_refs.value[0].node.value)
        self.assertEqual(Text('/dev/sdb'), disk_refs.value[0].path)

        ret = CdfGenerator(provider=store)._create_profile_descriptions(ret)
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('Profile_the_pool'), ret[0].name)
        self.assertEqual(1, len(ret[0].pools.value))
        self.assertEqual(Text('StorageSet-1__sns'), ret[0].pools.value[0])

    def test_disk_refs_can_be_empty(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>CLUSTER_ID>site>storage_set_count': 1,
                'cluster>CLUSTER_ID>storage_set>server_node_count': 1,
                'cluster>CLUSTER_ID>storage_set[0]>name': 'StorageSet-1',
                'cluster>CLUSTER_ID>storage_set[0]>server_nodes': ['srvnode_1'],
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns': {'stub': 1},
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>data': 1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>spare': 0,
                'cluster>cluster_id':
                'CLUSTER_ID',
                'server_node': {
                    'srvnode_1': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'server_node>srvnode_1>cluster_id':
                'CLUSTER_ID',
                'server_node>srvnode_1>name':
                'myhost',
                'server_node>srvnode_1>hostname':
                'myhost',
                'server_node>srvnode_1>network>data>interface_type':
                'o2ib',
                'server_node>srvnode_1>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'server_node>srvnode_1>s3_instances':
                1,
                'server_node>srvnode_1>storage>cvg':
                [{'data_devices': ['/dev/sdb'], 'metadata_devices': ['/dev/meta']}],
                'server_node>srvnode_1>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
            }
            return data.get(value)

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
                'cluster>CLUSTER_ID>site>storage_set_count':
                1,
                'cluster>CLUSTER_ID>storage_set>server_node_count':
                1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns': {'stub': 1},
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>data': 2,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>spare': 0,
                'cluster>CLUSTER_ID>storage_set[0]>name':
                'StorageSet-1',
                'cluster>CLUSTER_ID>storage_set[0]>server_nodes': ['MACH_ID'],
                'cluster>cluster_id':
                'CLUSTER_ID',
                'server_node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'server_node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>network>data>interface_type':
                'o2ib',
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'server_node>MACH_ID>s3_instances':
                1,
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_ID>storage>cvg[0]>metadata_devices':
                ['/dev/meta'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)

        with self.assertRaisesRegex(RuntimeError,
                                    r'Invalid storage set configuration'):
            CdfGenerator(provider=store)._create_pool_descriptions()

    def test_md_pool_ignored(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>CLUSTER_ID>site>storage_set_count':
                1,
                'cluster>CLUSTER_ID>storage_set>server_node_count':
                1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>md': {'1':2},
                'cluster>CLUSTER_ID>storage_set[0]>durability>md>data': 2,
                'cluster>CLUSTER_ID>storage_set[0]>durability>md>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>md>spare': 0,
                'cluster>CLUSTER_ID>storage_set[0]>name':
                'StorageSet-1',
                'cluster>CLUSTER_ID>storage_set[0]>server_nodes': ['MACH_ID'],
                'cluster>cluster_id':
                'CLUSTER_ID',
                'server_node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'server_node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>network>data>interface_type':
                'o2ib',
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'server_node>MACH_ID>s3_instances':
                1,
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_ID>storage>cvg[0]>metadata_devices':
                ['/dev/meta'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        ret = CdfGenerator(provider=store)._create_pool_descriptions()
        self.assertEqual(0, len(ret))

    def test_dix_pool_uses_metadata_devices(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>CLUSTER_ID>site>storage_set_count':
                1,
                'cluster>CLUSTER_ID>storage_set>server_node_count':
                1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix': {'1':2},
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix>data': 1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix>spare': 0,
                'cluster>CLUSTER_ID>storage_set[0]>name':
                'StorageSet-1',
                'cluster>CLUSTER_ID>storage_set[0]>server_nodes': ['MACH_ID'],
                'cluster>cluster_id':
                'CLUSTER_ID',
                'server_node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'server_node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>network>data>interface_type':
                'o2ib',
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'server_node>MACH_ID>s3_instances':
                1,
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_ID>storage>cvg[0]>metadata_devices':
                ['/dev/meta'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        ret = CdfGenerator(provider=store)._create_pool_descriptions()
        self.assertEqual(1, len(ret))
        diskrefs = ret[0].disk_refs.get()
        self.assertEqual(1, len(diskrefs))
        self.assertEqual(Text('/dev/meta'), diskrefs[0].path)

    def test_both_dix_and_sns_pools_can_exist(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>CLUSTER_ID>site>storage_set_count':
                1,
                'cluster>CLUSTER_ID>storage_set>server_node_count':
                1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix': {'1':2},
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix>data': 1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>dix>spare': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns': {'1':2},
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>data': 1,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>parity': 0,
                'cluster>CLUSTER_ID>storage_set[0]>durability>sns>spare': 0,
                'cluster>CLUSTER_ID>storage_set[0]>name':
                'StorageSet-1',
                'cluster>CLUSTER_ID>storage_set[0]>server_nodes': ['MACH_ID'],
                'cluster>cluster_id':
                'CLUSTER_ID',
                'server_node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'server_node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>network>data>interface_type':
                'o2ib',
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'server_node>MACH_ID>s3_instances':
                1,
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sda', '/dev/sdb'],
                'server_node>MACH_ID>storage>cvg[0]>metadata_devices':
                ['/dev/meta'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        ret = CdfGenerator(provider=store)._create_pool_descriptions()
        self.assertEqual(['sns', 'dix'], [t.type.name for t in ret])
        self.assertEqual(['StorageSet-1__sns', 'StorageSet-1__dix'],
                         [t.name.s for t in ret])

        diskrefs_sns = ret[0].disk_refs.get()
        self.assertEqual([Text('/dev/sda'), Text('/dev/sdb')],
                         [t.path for t in diskrefs_sns])

        diskrefs_dix = ret[1].disk_refs.get()
        self.assertEqual(1, len(diskrefs_dix))
        self.assertEqual(Text('/dev/meta'), diskrefs_dix[0].path)

    def test_metadata_is_hardcoded(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'server_node': {
                    'MACH_ID': 'stub'
                },
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>name': 'mynodename',
                'server_node>MACH_ID>storage>cvg':
                [{'data_devices': ['/dev/sdb'], 'metadata_devices': ['/dev/meta']}],
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'server_node>MACH_ID>s3_instances':
                1,
                'server_node>MACH_ID>network>data>interface_type':
                'o2ib'
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('/dev/vg_mynodename_md1/lv_raw_md1'),
                         (ret[0].m0_servers.value.value)[0].io_disks.meta_data.value)


    def test_multiple_nodes_supported(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'server_node': {
                    'MACH_ID': 'stub',
                    'MACH_2_ID': 'stub'
                },
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>site>storage_set_count':
                1,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set>server_node_count':
                2,
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set[0]>name':
                'StorageSet-1',
                'cluster>92f444df-87cc-4137-b680-aab3b35d1695>storage_set[0]>server_nodes':
                ['srvnode_1', 'srvnode_2'],
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>name': 'mynodename',
                'server_node>MACH_ID>network>data>interface_type':
                'o2ib',
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1'],
                'server_node>MACH_ID>s3_instances':
                1,
                'server_node>MACH_ID>storage>cvg':
                [{'data_devices': ['/dev/sdb'], 'metadata_devices': ['/dev/meta']}],
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_ID>storage>cvg[0]>metadata_devices':
                ['/dev/meta'],
                'server_node>MACH_2_ID>name':                'host-2',
                'server_node>MACH_2_ID>hostname':            'host-2',
                'server_node>MACH_2_ID>network>data>interface_type':                'tcp',
                'server_node>MACH_2_ID>network>data>private_interfaces':
                ['eno1'],
                'server_node>MACH_2_ID>s3_instances':                5,
                'server_node>MACH_2_ID>storage>cvg':
                [{'data_devices': ['/dev/sdb'], 'metadata_devices': ['/dev/meta']}],
                'server_node>MACH_2_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_2_ID>storage>cvg[0]>metadata_devices':
                ['/dev/meta'],
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
                'server_node': {
                    'MACH_ID': 'stub'
                },
                'server_node>MACH_ID>name': 'mynodename',
                'server_node>MACH_ID>hostname':
                'myhost',
                'server_node>MACH_ID>storage>cvg':
                [{'data_devices': ['/dev/sdb'], 'metadata_devices': ['/dev/meta']}],
                'server_node>MACH_ID>storage>cvg[0]>data_devices':
                ['/dev/sdb'],
                'server_node>MACH_ID>network>data>interface_type':
                None,
                'server_node>MACH_ID>s3_instances':
                1,
                'server_node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2']
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertEqual('None P', str(ret[0].data_iface_type))
