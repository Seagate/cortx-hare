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
#
import os
import tempfile
import unittest
import json
from typing import Any
from unittest.mock import Mock

import pkg_resources

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider, ValueProvider
from hare_mp.types import (DisksDesc, Disk, DList, M0ClientDesc, M0ServerDesc, Maybe,
                           MissingKeyError, PoolDesc, PoolType, Protocol, Text,
                           AllowedFailures, Layout)
from hare_mp.utils import Utils
from hax.util import KVAdapter


class TestTypes(unittest.TestCase):
    def test_m0clients(self):
        val = M0ClientDesc(name='other', instances=2)
        self.assertEqual('{ name = other, instances = 2 }', str(val))

    def test_protocol(self):
        self.assertEqual('P.tcp', str(Protocol.tcp))
        self.assertEqual('P.o2ib', str(Protocol.o2ib))

    def test_maybe_none(self):
        val = Maybe(None, 'P')
        self.assertEqual('None (P)', str(val))
        self.assertEqual('Some (P.tcp)', str(Maybe(Protocol.tcp, 'P')))

    def test_disks_empty(self):
        val = M0ServerDesc(runs_confd=Maybe(True, 'Bool'),
                           io_disks=DisksDesc(meta_data=Maybe(None, 'Text'),
                                              data=DList([], 'List Text')))
        self.assertEqual(
            '{ runs_confd = Some (True), io_disks = { meta_data = None (Text), data = [] : List Text } }',
            str(val))

    def test_pooldesc_empty(self):
        val = PoolDesc(name=Text('storage_set_name'),
                       disk_refs=Maybe(DList([], 'List DiskRef'), []),
                       data_units=0,
                       parity_units=0,
                       spare_units=Maybe(0, 'Natural'),
                       type=PoolType.sns,
                       allowed_failures=Maybe(None, 'AllowedFailures'))
        self.assertEqual(
            '{ name = "storage_set_name", disk_refs = Some ([] : List DiskRef), '
            'data_units = 0, parity_units = 0, spare_units = Some (0), type = T.PoolType.sns, '
            'allowed_failures = None (AllowedFailures) }',
            str(val))

    def test_m0server_with_disks(self):
        val = M0ServerDesc(
            runs_confd=Maybe(True, 'Bool'),
            io_disks=DisksDesc(
                meta_data=Maybe(None, 'Text'),
                data=DList([Text('/disk1'), Text('/disk2')], 'test')))
        self.assertEqual(
            '{ runs_confd = Some (True), io_disks = { meta_data = None (Text), data = ["/disk1", "/disk2"] } }',
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
            def new_kv(key: str, val: str):
                return {
                    'Key': key,
                    'CreateIndex': 1793,
                    'ModifyIndex': 1793,
                    'LockIndex': 0,
                    'Flags': 0,
                        'Value': val,
                    'Session': ''
                }


            store.get_machine_id = Mock(return_value='1114a50a6bf6f9c93ebd3c49d07d3fd4')
            store.get_machine_ids_for_service = Mock(return_value=['1114a50a6bf6f9c93ebd3c49d07d3fd4'])
            store.get_motr_clients = Mock(return_value=[])
            utils = Utils(store)
            kv = KVAdapter()
            def my_get(key: str, recurse: bool = False, allow_null: bool = False):
                if key == 'conf/node>1114a50a6bf6f9c93ebd3c49d07d3fd4>node_group':
                    return new_kv('conf/node>1114a50a6bf6f9c93ebd3c49d07d3fd4>node_group',
                                  "ssc-vm-1623.colo.seagate.com".encode())
                elif key == 'conf/node>9ec5de3a8b57493e8fc7bfae67ecd3b3>node_group':
                    return new_kv('conf/node>9ec5de3a8b57493e8fc7bfae67ecd3b3>node_group',
                                  "ssc-vm-1624.colo.seagate.com".encode())
                elif key == 'conf/node>846fd26885f8423a8da0626538ed47bc>node_group':
                    return new_kv('conf/node>846fd26885f8423a8da0626538ed47bc>node_group',
                                  "ssc-vm-1625.colo.seagate.com".encode())
                elif key == 'srvnode-1.data.private/drives/dev/sda':
                    return new_kv('srvnode-1.data.private/drives/dev/sda',
                                  json.dumps({"path": "/dev/sda",
                                              "size": "4096000",
                                              "blksize": "4096"}))
                elif key == 'srvnode-1.data.private/drives/dev/sdb':
                    return new_kv('srvnode-1.data.private/drives/dev/sdb',
                                  json.dumps({"path": "/dev/sdb",
                                              "size": "4096000",
                                              "blksize": "4096"}))
                elif key == 'srvnode-1.data.private/drives/dev/sdc':
                    return new_kv('srvnode-1.data.private/drives/dev/sdc',
                                  json.dumps({"path": "/dev/sdc",
                                              "size": "4096000",
                                              "blksize": "4096"}))
                elif key == 'srvnode-1.data.private/drives/dev/sdg':
                    return new_kv('srvnode-1.data.private/drives/dev/sdg',
                                  json.dumps({"path": "/dev/sdg",
                                              "size": "4096000",
                                              "blksize": "4096"}))
                elif key == 'srvnode-1.data.private/drives/dev/sdh':
                    return new_kv('srvnode-1.data.private/drives/dev/sdh',
                                  json.dumps({"path": "/dev/sdh",
                                              "size": "4096000",
                                              "blksize": "4096"}))
                elif key == 'srvnode-1.data.private/drives/dev/sdi':
                    return new_kv('srvnode-1.data.private/drives/dev/sdi',
                                  json.dumps({"path": "/dev/sdi",
                                              "size": "4096000",
                                              "blksize": "4096"}))
                elif key == 'srvnode-1.data.private/facts':
                    return new_kv('srvnode-1.data.private/facts',
                                  json.dumps({"processorcount": "16",
                                              "memorysize_mb": "4096.123"}))
                if allow_null:
                    return None
                else:
                    raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

            kv.kv_get = my_get
            utils.kv = kv
            #
            # the method will raise an exception if either
            # Dhall is unhappy or some values are not found in ConfStore
            cdf = CdfGenerator(provider=store)
            cdf.utils = utils
            cdf._get_m0d_per_cvg = Mock(return_value=1)
            cdf.generate()
        finally:
            os.unlink(path)

    def test_it_works(self):
        store = ValueProvider()
        motr_store = ValueProvider()
        def new_kv(key: str, val: str):
            return {
                'Key': key,
                'CreateIndex': 1793,
                'ModifyIndex': 1793,
                'LockIndex': 0,
                'Flags': 0,
                'Value': val,
                'Session': ''
            }


        def ret_values(value: str) -> Any:
            data = {
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node>MACH_ID>name': 'myhost',
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_fqdn':
                    'srvnode-1.data.private',
                'node>MACH_ID>components':
                [{'name':'hare'}, {'name': 'motr'}, {'name': 's3'}],
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[1]>devices>data':
                ['/dev/sdc'],
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'node>MACH_ID>num_cvg':
                2,
                'node>MACH_ID>cvg':
                [{'devices': {'data': ['/dev/sdb', '/dev/sdc'], 'metadata': ['/dev/meta', '/dev/meta1']}}],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta'],
                'node>MACH_ID>cvg[1]>devices>metadata':
                ['/dev/meta1'],
                'cortx>s3>service_instances':
                1,
                'cortx>motr>interface_type':
                'tcp',
                'cortx>motr>client_instances':
                2,
                'node>MACH_ID>num_cvg': 1,
                'cluster>num_storage_set':
                1,
                'cluster>storage_set>server_node_count':
                1,
                'cluster>storage_set[0]>name':
                'StorageSet-1',
                'cluster>storage_set[0]>nodes': ['MACH_ID'],
                'cluster>storage_set[0]>durability>sns': {'stub': 1},
                'cluster>storage_set[0]>durability>sns>data': 1,
                'cluster>storage_set[0]>durability>sns>parity': 0,
                'cluster>storage_set[0]>durability>sns>spare': 0,
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                }
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])
        store.get_motr_clients = Mock(return_value=[])
        utils = Utils(store)
        kv = KVAdapter()
        def my_get(key: str, recurse: bool = False, allow_null: bool = False):
            if key == 'conf/node>MACH_ID>node_group' :
                return new_kv('conf/node>MACH_ID>node_group',
                              "myhost".encode())
            elif key == 'srvnode-1.data.private/drives/dev/sdb':
                return new_kv('srvnode-1.data.private/drives/dev/sdb',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/drives/dev/sdc':
                return new_kv('srvnode-1.data.private/drives/dev/sdc',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/facts':
                return new_kv('srvnode-1.data.private/facts',
                              json.dumps({"processorcount": "16",
                                          "memorysize_mb": "4096.123"}))
            if allow_null:
                return None
            else:
                raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

        kv.kv_get = my_get
        utils.kv = kv

        def ret_motr_mdvalues(value: str) -> Any:
            data = {
                'server>MACH_ID>cvg[0]>m0d':
                ['/dev/vg_srvnode-1_md1/lv_raw_md1'],
                'server>MACH_ID>cvg[0]>m0d[0]>md_seg1':
                '/dev/vg_srvnode-1_md1/lv_raw_md1',
                'server>MACH_ID>cvg[1]>m0d':
                ['/dev/vg_srvnode-1_md2/lv_raw_md2'],
                'server>MACH_ID>cvg[1]>m0d[0]>md_seg1':
                '/dev/vg_srvnode-1_md2/lv_raw_md2'
            }
            return data.get(value)

        motr_store._raw_get = Mock(side_effect=ret_motr_mdvalues)

        cdf = CdfGenerator(provider=store)
        cdf.utils = utils
        cdf.generate()

    def test_provided_values_respected(self):
        store = ValueProvider()
        motr_store = ValueProvider()
        def new_kv(key: str, val: str):
            return {
                'Key': key,
                'CreateIndex': 1793,
                'ModifyIndex': 1793,
                'LockIndex': 0,
                'Flags': 0,
                'Value': val,
                'Session': ''
            }



        def ret_values(value: str) -> Any:
            data = {
                'cluster>num_storage_set': 1,
                'cluster>storage_set>server_node_count':
                1,
                'cluster>storage_set[0]>name': 'StorageSet-1',
                'cluster>storage_set[0]>durability>sns': {'a': 42},
                'cluster>storage_set[0]>durability>sns>data': 1,
                'cluster>storage_set[0]>durability>sns>parity': 0,
                'cluster>storage_set[0]>durability>sns>spare': 0,
                'cluster>storage_set[0]>nodes': ['MACH_ID'],
                'cluster>storage_set>server_node_count': 1,
                'node>MACH_ID>cluster_id': 'CLUSTER_ID',
                'node': {'MACH_ID': {'cluster_id': 'CLUSTER_ID'}},
                'node>MACH_ID>cluster_id': 'CLUSTER_ID',
                'node>MACH_ID>components':
                [{'name':'hare'}, {'name': 'motr'}, {'name': 's3'},
                 {'name': 'other'}],
                'node>MACH_ID>num_cvg': 2,
                'node>MACH_ID>cvg':
                [{'devices': {'data': ['/dev/sdb', '/dev/sdc'], 'metadata': ['/dev/meta', '/dev/meta1']}}],
                'node>MACH_ID>cvg[0]>devices>data': ['/dev/sdb'],
                'node>MACH_ID>cvg[0]>devices>metadata': ['/dev/meta'],
                'node>MACH_ID>cvg[1]>devices>data': ['/dev/sdc'],
                'node>MACH_ID>cvg[1]>devices>metadata': ['/dev/meta1'],
                'node>MACH_ID>hostname':                'myhost',
                'node>MACH_ID>name': 'mynodename',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_fqdn':
                    'srvnode-1.data.private',
                'node>MACH_ID>network>data>private_interfaces':                ['eth1', 'eno2'],
                'cortx>s3>service_instances':                1,
                'cortx>motr>interface_type':                'o2ib',
            }
            if value in data:
                return data.get(value)
            else:
                return None

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])
        store.get_motr_clients = Mock(return_value=
                                      [{'name': 'other',
                                        'num_instances' : 2}])
        store.get_machine_ids_for_component = Mock(return_value=['MACH_ID'])
        utils = Utils(store)
        kv = KVAdapter()
        def my_get(key: str, recurse: bool = False, allow_null: bool = False):
            if key == 'conf/node>MACH_ID>node_group' :
                return new_kv('conf/node>MACH_ID>node_group',
                              "mynodename".encode())
            elif key == 'srvnode-1.data.private/drives/dev/sdb':
                return new_kv('srvnode-1.data.private/drives/dev/sdb',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/drives/dev/sdc':
                return new_kv('srvnode-1.data.private/drives/dev/sdc',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/facts':
                return new_kv('srvnode-1.data.private/facts',
                              json.dumps({"processorcount": "16",
                                          "memorysize_mb": "4096.123"}))
            if allow_null:
                return None
            else:
                raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

        kv.kv_get = my_get
        utils.kv = kv

        def ret_motr_mdvalues(value: str) -> Any:
            data = {
                'server>MACH_ID>cvg[0]>m0d':
                ['/dev/vg_srvnode-1_md1/lv_raw_md1'],
                'server>MACH_ID>cvg[0]>m0d[0]>md_seg1':
                '/dev/vg_srvnode-1_md1/lv_raw_md1',
                'server>MACH_ID>cvg[1]>m0d':
                ['/dev/vg_srvnode-1_md2/lv_raw_md2'],
                'server>MACH_ID>cvg[1]>m0d[0]>md_seg1':
                '/dev/vg_srvnode-1_md2/lv_raw_md2'
            }
            return data.get(value)

        motr_store._raw_get = Mock(side_effect=ret_motr_mdvalues)

        cdf = CdfGenerator(provider=store)
        cdf.utils = utils
        ret = cdf._create_node_descriptions()

        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('srvnode-1.data.private'), ret[0].hostname)
        self.assertEqual(Text('eth1'), ret[0].data_iface)
        clients = ret[0].m0_clients.value.value
        self.assertIsInstance(clients, list)
        self.assertEqual(1, len(clients))
        self.assertEqual(Text('other'), clients[0].name)
        self.assertEqual(2, clients[0].instances)


        cdf = CdfGenerator(provider=store)
        cdf.utils = utils
        ret = cdf._create_pool_descriptions()

        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('StorageSet-1__sns'), ret[0].name)
        self.assertEqual(PoolType.sns, ret[0].type)
        self.assertEqual(1, ret[0].data_units)
        self.assertEqual(0, ret[0].parity_units)
        self.assertEqual(0, ret[0].spare_units.get())
        disk_refs = ret[0].disk_refs.value
        self.assertEqual(Text('srvnode-1.data.private'),
                         disk_refs.value[0].node.value)
        self.assertEqual(Text('/dev/sdb'), disk_refs.value[0].path)
        self.assertEqual(0, ret[0].allowed_failures.value.site)
        self.assertEqual(0, ret[0].allowed_failures.value.rack)
        self.assertEqual(0, ret[0].allowed_failures.value.encl)
        self.assertEqual(0, ret[0].allowed_failures.value.ctrl)
        self.assertEqual(0, ret[0].allowed_failures.value.disk)

        cdf = CdfGenerator(provider=store)
        cdf.utils = utils
        ret = cdf._create_profile_descriptions(ret)

        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('Profile_the_pool'), ret[0].name)
        self.assertEqual(1, len(ret[0].pools.value))
        self.assertEqual(Text('StorageSet-1__sns'), ret[0].pools.value[0])

    def test_allowed_failure_generation(self):
        layout_4_2_0 = Layout(data=4, parity=2,spare=0)
        ret = self.allowed_failure_generation(layout_4_2_0)

        self.assertEqual(1, len(ret))
        self.assertEqual(layout_4_2_0.data, ret[0].data_units)
        self.assertEqual(layout_4_2_0.parity, ret[0].parity_units)
        self.assertEqual(layout_4_2_0.spare, ret[0].spare_units.get())
        self.assertEqual(0, ret[0].allowed_failures.value.site)
        self.assertEqual(0, ret[0].allowed_failures.value.rack)
        self.assertEqual(1, ret[0].allowed_failures.value.encl)
        self.assertEqual(2, ret[0].allowed_failures.value.ctrl)
        self.assertEqual(2, ret[0].allowed_failures.value.disk)

        layout_4_2_2 = Layout(data=4, parity=2,spare=2)
        ret = self.allowed_failure_generation(layout_4_2_2)

        self.assertEqual(1, len(ret))
        self.assertEqual(layout_4_2_2.data, ret[0].data_units)
        self.assertEqual(layout_4_2_2.parity, ret[0].parity_units)
        self.assertEqual(layout_4_2_2.spare, ret[0].spare_units.get())
        self.assertEqual(0, ret[0].allowed_failures.value.site)
        self.assertEqual(0, ret[0].allowed_failures.value.rack)
        self.assertEqual(0, ret[0].allowed_failures.value.encl)
        self.assertEqual(0, ret[0].allowed_failures.value.ctrl)
        self.assertEqual(2, ret[0].allowed_failures.value.disk)


    # Currently only Layout is provided as input, in future we can add more
    def allowed_failure_generation(self, layout: Layout):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>num_storage_set': 1,
                'cluster>storage_set[0]>name': 'StorageSet-1',
                'cluster>storage_set[0]>durability>sns':
                {'data': 4, 'parity' : 2, 'spare' : 0},
                'cluster>storage_set[0]>durability>sns>data': layout.data,
                'cluster>storage_set[0]>durability>sns>parity': layout.parity,
                'cluster>storage_set[0]>durability>sns>spare': layout.spare,
                'cluster>storage_set[0]>nodes': ['MACH_ID1', 'MACH_ID2', 'MACH_ID3'],
                'cluster>storage_set>server_node_count': 3,
                'node>MACH_ID>cluster_id': 'CLUSTER_ID',
                'node': {'MACH_ID1': {'cluster_id': 'CLUSTER_ID'}},
                'node>MACH_ID1>cluster_id': 'CLUSTER_ID',
                'node>MACH_ID2>cluster_id': 'CLUSTER_ID',
                'node>MACH_ID3>cluster_id': 'CLUSTER_ID',
                'node>MACH_ID1>cvg':
                [{'devices': {'data': ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd'], 'metadata': ['/dev/meta1']}},
                 {'devices': {'data': ['/dev/sde', '/dev/sdf', '/dev/sdg', '/dev/sdh'], 'metadata': ['/dev/meta2']}}],
                'node>MACH_ID2>cvg':
                [{'devices': {'data': ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd'], 'metadata': ['/dev/meta1']}},
                 {'devices': {'data': ['/dev/sde', '/dev/sdf', '/dev/sdg', '/dev/sdh'], 'metadata': ['/dev/meta2']}}],
                'node>MACH_ID3>cvg':
                [{'devices': {'data': ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd'], 'metadata': ['/dev/meta1']}},
                 {'devices': {'data': ['/dev/sde', '/dev/sdf', '/dev/sdg', '/dev/sdh'], 'metadata': ['/dev/meta2']}}],
                'node>MACH_ID1>num_cvg': '2',
                'node>MACH_ID1>cvg[0]>devices>data': ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd'],
                'node>MACH_ID1>cvg[1]>devices>data': ['/dev/sde', '/dev/sdf', '/dev/sdg', '/dev/sdh'],
                'node>MACH_ID1>cvg[0]>devices>metadata': ['/dev/meta1'],
                'node>MACH_ID1>cvg[1]>devices>metadata': ['/dev/meta2'],
                'node>MACH_ID1>hostname':                'myhost',
                'node>MACH_ID1>name': 'mynodename',
                'node>MACH_ID1>type': 'storage_node',
                'node>MACH_ID1>network>data>private_fqdn':
                    'srvnode-1.data.private',
                'node>MACH_ID1>network>data>private_interfaces':                ['eth1', 'eno2'],
                'cortx>s3>service_instances':                1,
                'cortx>motr>interface_type':                'o2ib',
                'node>MACH_ID2>num_cvg': '2',
                'node>MACH_ID2>cvg[0]>devices>data': ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd'],
                'node>MACH_ID2>cvg[1]>devices>data': ['/dev/sde', '/dev/sdf', '/dev/sdg', '/dev/sdh'],
                'node>MACH_ID2>cvg[0]>devices>metadata': ['/dev/meta1'],
                'node>MACH_ID2>cvg[1]>devices>metadata': ['/dev/meta2'],
                'node>MACH_ID2>hostname':                'myhost',
                'node>MACH_ID2>name': 'mynodename',
                'node>MACH_ID2>type': 'storage_node',
                'node>MACH_ID2>network>data>private_fqdn':
                    'srvnode-2.data.private',
                'node>MACH_ID2>network>data>private_interfaces':                ['eth1', 'eno2'],
                'cortx>s3>service_instances':                1,
                'cortx>motr>interface_type':                'o2ib',
                'node>MACH_ID3>num_cvg': '2',
                'node>MACH_ID3>cvg[0]>devices>data': ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd'],
                'node>MACH_ID3>cvg[1]>devices>data': ['/dev/sde', '/dev/sdf', '/dev/sdg', '/dev/sdh'],
                'node>MACH_ID3>cvg[0]>devices>metadata': ['/dev/meta1'],
                'node>MACH_ID3>cvg[1]>devices>metadata': ['/dev/meta2'],
                'node>MACH_ID3>hostname':                'myhost',
                'node>MACH_ID3>name': 'mynodename',
                'node>MACH_ID3>type': 'storage_node',
                'node>MACH_ID3>network>data>private_fqdn':
                    'srvnode-3.data.private',
                'node>MACH_ID3>network>data>private_interfaces':                ['eth1', 'eno2'],
                'cortx>s3>service_instances':                1,
                'cortx>motr>interface_type':                'o2ib',
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID1')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID1',
                                                               'MACH_ID2',
                                                               'MACH_ID3'])

        ret = CdfGenerator(provider=store)._create_pool_descriptions()
        self.assertIsInstance(ret, list)
        return ret

    def test_disk_refs_can_be_empty(self):
        store = ValueProvider()

        def new_kv(key: str, val: str):
            return {
                'Key': key,
                'CreateIndex': 1793,
                'ModifyIndex': 1793,
                'LockIndex': 0,
                'Flags': 0,
                'Value': val,
                'Session': ''
            }

        def ret_values(value: str) -> Any:
            data = {
                'node>MACH_ID>num_cvg': 1,
                'cluster>num_storage_set': 1,
                'cluster>storage_set>server_node_count': 1,
                'cluster>storage_set[0]>name': 'StorageSet-1',
                'cluster>storage_set[0]>nodes': ['MACH_ID'],
                'cluster>storage_set[0]>durability>sns': {'stub': 1},
                'cluster>storage_set[0]>durability>sns>data': 1,
                'cluster>storage_set[0]>durability>sns>parity': 0,
                'cluster>storage_set[0]>durability>sns>spare': 0,
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node>MACH_ID>name':
                'myhost',
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>components':
                [{'name':'hare'}, {'name': 'motr'}, {'name': 's3'}],
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_fqdn':
                    'srvnode-1.data.private',
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cortx>s3>service_instances':
                1,
                'node>MACH_ID>num_cvg':
                2,
                'cortx>motr>interface_type':
                'o2ib',
                'cortx>motr>client_instances':
                2,
                'node>MACH_ID>cvg':
                [{'devices': {'data': ['/dev/sdb', '/dev/sdc'], 'metadata': ['/dev/meta', '/dev/meta1']}}],
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[1]>devices>data':
                ['/dev/sdc'],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta1'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])
        store.get_motr_clients = Mock(return_value=[])
        cdf = CdfGenerator(provider=store)
        cdf._get_m0d_per_cvg = Mock(return_value=1)
        utils = Utils(store)
        kv = KVAdapter()
        def my_get(key: str, recurse: bool = False, allow_null: bool = False):
            if key == 'conf/node>MACH_ID>node_group' :
                return new_kv('conf/node>MACH_ID>node_group',
                              "myhost".encode())
            elif key == 'srvnode-1.data.private/drives/dev/sdb':
                return new_kv('srvnode-1.data.private/drives/dev/sdb',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/drives/dev/sdc':
                return new_kv('srvnode-1.data.private/drives/dev/sdc',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/facts':
                return new_kv('srvnode-1.data.private/facts',
                              json.dumps({"processorcount": "16",
                                          "memorysize_mb": "4096.123"}))
            if allow_null:
                return None
            else:
                raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')


        kv.kv_get = my_get
        utils.kv = kv
        cdf.utils = utils
        cdf.generate()

    def test_invalid_storage_set_configuration_rejected(self):
        ''' This test case checks whether exception will be raise if total
            number of data devices are less than
            data_units + parity_units + spare_units
        '''
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>num_storage_set':
                1,
                'cluster>storage_set>server_node_count':
                1,
                'cluster>storage_set[0]>durability>sns': {'stub': 1},
                'cluster>storage_set[0]>durability>sns>data': 4,
                'cluster>storage_set[0]>durability>sns>parity': 0,
                'cluster>storage_set[0]>durability>sns>spare': 0,
                'cluster>storage_set[0]>name':
                'StorageSet-1',
                'cluster>storage_set[0]>nodes': ['MACH_ID'],
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cortx>s3>service_instances':
                1,
                'node>MACH_ID>num_cvg':
                2,
                'cortx>motr>interface_type':
                'o2ib',
                'cortx>motr>client_instances':
                2,
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta'],
                'node>MACH_ID>cvg[1]>devices>data':
                ['/dev/sdc'],
                'node>MACH_ID>cvg[1]>devices>metadata':
                ['/dev/meta1'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])

        with self.assertRaisesRegex(RuntimeError,
                                    r'Invalid storage set configuration'):
            CdfGenerator(provider=store)._create_pool_descriptions()

    def test_md_pool_ignored(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>num_storage_set':
                1,
                'cluster>storage_set>server_node_count':
                1,
                'cluster>storage_set[0]>durability>md': {'1':2},
                'cluster>storage_set[0]>durability>md>data': 2,
                'cluster>storage_set[0]>durability>md>parity': 0,
                'cluster>storage_set[0]>durability>md>spare': 0,
                'cluster>storage_set[0]>name':
                'StorageSet-1',
                'cluster>storage_set[0]>nodes': ['MACH_ID'],
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cortx>s3>service_instances':
                1,
                'cortx>motr>interface_type':
                'o2ib',
                'cortx>motr>client_instances':
                2,
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[0]>devices>metadata':
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
                'node>MACH_ID>num_cvg': 1,
                'cluster>num_storage_set':
                1,
                'cluster>storage_set>server_node_count':
                1,
                'cluster>storage_set[0]>durability>dix': {'1':2},
                'cluster>storage_set[0]>durability>dix>data': 1,
                'cluster>storage_set[0]>durability>dix>parity': 0,
                'cluster>storage_set[0]>durability>dix>spare': 0,
                'cluster>storage_set[0]>name':
                'StorageSet-1',
                'cluster>storage_set[0]>nodes': ['MACH_ID'],
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_fqdn':
                    'srvnode-1.data.private',
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cortx>s3>service_instances':
                1,
                'node>MACH_ID>num_cvg':
                2,
                'cortx>motr>interface_type':
                'o2ib',
                'cortx>motr>client_instances':
                2,
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta'],
                'node>MACH_ID>cvg[1]>devices>data':
                ['/dev/sdc'],
                'node>MACH_ID>cvg[1]>devices>metadata':
                ['/dev/meta1'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])
        ret = CdfGenerator(provider=store)._create_pool_descriptions()
        self.assertEqual(1, len(ret))
        diskrefs = ret[0].disk_refs.get()
        self.assertEqual(2, len(diskrefs))
        self.assertEqual(Text('/dev/meta'), diskrefs[0].path)

    def test_both_dix_and_sns_pools_can_exist(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'node>MACH_ID>num_cvg': 1,
                'cluster>num_storage_set':
                1,
                'cluster>storage_set>server_node_count':
                1,
                'cluster>storage_set[0]>durability>dix': {'1':2},
                'cluster>storage_set[0]>durability>dix>data': 1,
                'cluster>storage_set[0]>durability>dix>parity': 0,
                'cluster>storage_set[0]>durability>dix>spare': 0,
                'cluster>storage_set[0]>durability>sns': {'1':2},
                'cluster>storage_set[0]>durability>sns>data': 1,
                'cluster>storage_set[0]>durability>sns>parity': 0,
                'cluster>storage_set[0]>durability>sns>spare': 0,
                'cluster>storage_set[0]>name':
                'StorageSet-1',
                'cluster>storage_set[0]>nodes': ['MACH_ID'],
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node': {
                    'MACH_ID': {
                        'cluster_id': 'CLUSTER_ID'
                    }
                },
                'node>MACH_ID>cluster_id':
                'CLUSTER_ID',
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_fqdn':
                    'srvnode-1.data.private',
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cortx>s3>service_instances':
                1,
                'node>MACH_ID>num_cvg':
                2,
                'cortx>motr>interface_type':
                'o2ib',
                'cortx>motr>client_instances':
                2,
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sda', '/dev/sdb'],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta'],
                'node>MACH_ID>cvg[1]>devices>data':
                ['/dev/sdc', '/dev/sdd'],
                'node>MACH_ID>cvg[1]>devices>metadata':
                ['/dev/meta1'],
            }
            return data.get(value)

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])
        ret = CdfGenerator(provider=store)._create_pool_descriptions()
        self.assertEqual(['sns', 'dix'], [t.type.name for t in ret])
        self.assertEqual(['StorageSet-1__sns', 'StorageSet-1__dix'],
                         [t.name.s for t in ret])

        diskrefs_sns = ret[0].disk_refs.get()
        self.assertEqual([Text('/dev/sda'), Text('/dev/sdb'), Text('/dev/sdc'), Text('/dev/sdd')],
                         [t.path for t in diskrefs_sns])

        diskrefs_dix = ret[1].disk_refs.get()
        self.assertEqual(2, len(diskrefs_dix))
        self.assertEqual(Text('/dev/meta'), diskrefs_dix[0].path)

    def test_metadata_is_hardcoded(self):
        store = ValueProvider()
        motr_store = ValueProvider()
        def new_kv(key: str, val: str):
            return {
                'Key': key,
                'CreateIndex': 1793,
                'ModifyIndex': 1793,
                'LockIndex': 0,
                'Flags': 0,
                'Value': val,
                'Session': ''
            }


        def ret_values(value: str) -> Any:
            data = {
                'node': {
                    'MACH_ID': 'stub'
                },
                'node>MACH_ID>hostname':
                'myhost',
                'cortx>hare>hax>endpoints':
                ['tcp://myhost:22001'],
                'node>MACH_ID>name': 'mynodename',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>components':
                [{'name':'hare'}, {'name': 'motr', 'services': ['io']}, {'name': 's3'}],
                'node>MACH_ID>cvg':
                [{'devices': {'data': ['/dev/sdb'], 'metadata': ['/dev/meta1']}},
                 {'devices': {'data': ['/dev/sdc'], 'metadata': ['/dev/meta2']}}],
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[1]>devices>data':
                ['/dev/sdc'],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta1'],
                'node>MACH_ID>cvg[1]>devices>metadata':
                ['/dev/meta2'],
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2'],
                'cortx>s3>service_instances':
                1,
                'cortx>motr>transport_type':
                'libfab',
                'cortx>motr>interface_type':
                'o2ib',
                'cortx>motr>client_instances':
                2,
                'node>MACH_ID>network>data>private_fqdn':
                    'srvnode-1.data.private',
            }
            if value in data:
                return data[value]
            else:
                return None

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])
        store.get_motr_clients = Mock(return_value=[])
        utils = Utils(store)
        kv = KVAdapter()
        def my_get(key: str, recurse: bool = False, allow_null: bool = False):
            if key == 'conf/node>MACH_ID>node_group' :
                return new_kv('conf/node>MACH_ID>node_group',
                              "mynodename".encode())
            elif key == 'srvnode-1.data.private/drives/dev/sdb':
                return new_kv('srvnode-1.data.private/drives/dev/sdb',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/drives/dev/sdc':
                return new_kv('srvnode-1.data.private/drives/dev/sdc',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/facts':
                return new_kv('srvnode-1.data.private/facts',
                              json.dumps({"processorcount": "16",
                                          "memorysize_mb": "4096.123"}))
            if allow_null:
                return None
            else:
                raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

        kv.kv_get = my_get
        utils.kv = kv

        def ret_motr_mdvalues(value: str) -> Any:
            data = {
                'server>MACH_ID>cvg[0]>m0d':
                ['/dev/vg_srvnode-1_md1/lv_raw_md1'],
                'server>MACH_ID>cvg[0]>m0d[0]>md_seg1':
                '/dev/vg_srvnode-1_md1/lv_raw_md1',
                'server>MACH_ID>cvg[1]>m0d':
                ['/dev/vg_srvnode-1_md2/lv_raw_md2'],
                'server>MACH_ID>cvg[1]>m0d[0]>md_seg1':
                '/dev/vg_srvnode-1_md2/lv_raw_md2'
            }
            return data.get(value)

        motr_store._raw_get = Mock(side_effect=ret_motr_mdvalues)


        cdf = CdfGenerator(provider=store)
        cdf.utils = utils
        ret = cdf._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('/dev/meta1'),
                         (ret[0].m0_servers.value.value)[0].io_disks.meta_data.value)
        self.assertEqual(Text('/dev/meta2'),
                         (ret[0].m0_servers.value.value)[1].io_disks.meta_data.value)


    def test_multiple_nodes_supported(self):
        store = ValueProvider()
        def new_kv(key: str, val: str):
            return {
                'Key': key,
                'CreateIndex': 1793,
                'ModifyIndex': 1793,
                'LockIndex': 0,
                'Flags': 0,
                'Value': val,
                'Session': ''
            }


        def ret_values(value: str) -> Any:
            data = {
                'node': {
                    'MACH_ID': 'stub',
                    'MACH_2_ID': 'stub'
                },
                'cluster>num_storage_set':
                1,
                'cluster>storage_set>server_node_count':
                2,
                'cluster>storage_set[0]>name':
                'StorageSet-1',
                'cluster>storage_set[0]>nodes':
                ['srvnode_1', 'srvnode_2'],
                'cortx>hare>hax>endpoints':
                ['tcp://srvnode-1.data.private:22001',
                 'tcp://srvnode-2.data.private:22001'],
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>name': 'mynodename',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>network>data>private_fqdn':
                'srvnode-1.data.private',
                'node>MACH_ID>components':
                [{'name':'hare'}, {'name': 'motr'}, {'name': 's3'},
                 {'name': 'other'}],
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1'],
                'node>MACH_ID>cvg':
                [{'devices': {'data': ['/dev/sdb'], 'metadata': ['/dev/meta']}}],
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta'],
                'node>MACH_2_ID>name':                'host-2',
                'node>MACH_2_ID>hostname':            'host-2',
                'node>MACH_2_ID>type':                'storage_node',
                'cortx>motr>interface_type':                'tcp',
                'node>MACH_2_ID>network>data>private_fqdn':
                'srvnode-2.data.private',
                'node>MACH_2_ID>components':
                [{'name':'hare'}, {'name': 'motr'}, {'name': 's3'},
                 {'name': 'other'}],
                'node>MACH_2_ID>network>data>private_interfaces':
                ['eth1'],
                'cortx>motr>transport_type':
                'libfab',
                'cortx>s3>service_instances':                1,
                'cortx>motr>client_instances':                2,
                'node>MACH_2_ID>cvg':
                [{'devices': {'data': ['/dev/sdb'], 'metadata': ['/dev/meta']}}],
                'node>MACH_2_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_2_ID>cvg[0]>devices>metadata':
                ['/dev/meta'],
            }
            if value in data:
                return data[value]
            else:
                return None

        store._raw_get = Mock(side_effect=ret_values)

        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID',
                                                               'MACH_2_ID'])
        store.get_motr_clients = Mock(return_value=
                                [{'name': 'other',
                                'num_instances' : 2}])
        store.get_machine_ids_for_component = Mock(return_value=['MACH_ID',
                                                                 'MACH_2_ID'])
        utils = Utils(store)
        kv = KVAdapter()
        def my_get(key: str, recurse: bool = False, allow_null: bool = False):
            if key == 'conf/node>MACH_ID>node_group' :
                return new_kv('conf/node>MACH_ID>node_group',
                              "mynodename".encode())
            elif key == 'conf/node>MACH_2_ID>node_group' :
                return new_kv('conf/node>MACH_2_ID>node_group',
                              "host-2".encode())
            elif key == 'srvnode-1.data.private/drives/dev/sdb':
                return new_kv('srvnode-1.data.private/drives/dev/sdb',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/drives/dev/sdc':
                return new_kv('srvnode-1.data.private/drives/dev/sdc',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/facts':
                return new_kv('srvnode-1.data.private/facts',
                              json.dumps({"processorcount": "16",
                                          "memorysize_mb": "4096.123"}))
            elif key == 'srvnode-2.data.private/drives/dev/sdb':
                return new_kv('srvnode-1.data.private/drives/dev/sdb',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-2.data.private/drives/dev/sdc':
                return new_kv('srvnode-1.data.private/drives/dev/sdc',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-2.data.private/facts':
                return new_kv('srvnode-1.data.private/facts',
                              json.dumps({"processorcount": "16",
                                          "memorysize_mb": "4096.123"}))

            if allow_null:
                return None
            else:
                raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')

        kv.kv_get = my_get
        utils.kv = kv



        cdf = CdfGenerator(provider=store)
        cdf.utils = utils
        cdf._get_m0d_per_cvg = Mock(return_value=1)
        ret = cdf._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(2, len(ret))
        self.assertIn(Text('srvnode-1.data.private'),
                      [ret[0].hostname, ret[1].hostname])
        self.assertEqual(Text('eth1'), ret[0].data_iface)
        clients = ret[0].m0_clients.value.value
        self.assertIsInstance(clients, list)
        self.assertEqual(1, len(clients))
        self.assertEqual(Text('other'), clients[0].name)
        self.assertEqual(2, clients[0].instances)
        self.assertIn(Text('srvnode-2.data.private'),
                      [ret[0].hostname, ret[1].hostname])
        self.assertEqual(Text('eth1'), ret[1].data_iface)
        clients = ret[1].m0_clients.value.value
        self.assertIsInstance(clients, list)
        self.assertEqual(1, len(clients))
        self.assertEqual(Text('other'), clients[0].name)
        self.assertEqual(2, clients[0].instances)
        self.assertEqual('Some (P.tcp)', str(ret[0].data_iface_type))
        self.assertEqual('Some (P.tcp)', str(ret[1].data_iface_type))

    def test_iface_type_can_be_null(self):
        store = ValueProvider()

        def new_kv(key: str, val: str):
            return {
                'Key': key,
                'CreateIndex': 1793,
                'ModifyIndex': 1793,
                'LockIndex': 0,
                'Flags': 0,
                'Value': val,
                'Session': ''
            }

        def ret_values(value: str) -> Any:
            data = {
                'node': {
                    'MACH_ID': 'stub'
                },
                'node>MACH_ID>name': 'mynodename',
                'node>MACH_ID>hostname':
                'myhost',
                'node>MACH_ID>type': 'storage_node',
                'node>MACH_ID>components':
                [{'name':'hare'}, {'name': 'motr'}, {'name': 's3'}],
                'node>MACH_ID>cvg':
                [{'devices': {'data': ['/dev/sdb'], 'metadata': ['/dev/meta']}}],
                'node>MACH_ID>cvg[0]>devices>data':
                ['/dev/sdb'],
                'node>MACH_ID>cvg[0]>devices>metadata':
                ['/dev/meta1'],
                'node>MACH_ID>network>data>private_fqdn':
                    'srvnode-1.data.private',
                'cortx>hare>hax>endpoints':
                ['tcp://myhost:22001'],
                'cortx>s3>service_instances':
                1,
                'cortx>motr>interface_type':
                None,
                'cortx>motr>client_instances':
                2,
                'cortx>motr>transport_type':
                'libfab',
                'node>MACH_ID>network>data>private_interfaces':
                ['eth1', 'eno2']
            }
            if value in data:
                return data[value]
            else:
                return None

        store._raw_get = Mock(side_effect=ret_values)
        store.get_machine_id = Mock(return_value='MACH_ID')
        store.get_machine_ids_for_service = Mock(return_value=['MACH_ID'])
        store.get_motr_clients = Mock(return_value=[])
        cdf = CdfGenerator(provider=store)
        utils = Utils(store)
        kv = KVAdapter()
        def my_get(key: str, recurse: bool = False, allow_null: bool = False):
            if key == 'conf/node>MACH_ID>node_group':
                return new_kv('conf/node>MACH_ID>node_group',
                              "mynodename".encode())
            elif key == 'srvnode-1.data.private/drives/dev/sdb':
                return new_kv('srvnode-1.data.private/drives/dev/sdb',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/drives/dev/sdc':
                return new_kv('srvnode-1.data.private/drives/dev/sdc',
                              json.dumps({"path": "/dev/sdb",
                                          "size": "4096000",
                                          "blksize": "4096"}))
            elif key == 'srvnode-1.data.private/facts':
                return new_kv('srvnode-1.data.private/facts',
                              json.dumps({"processorcount": "16",
                                          "memorysize_mb": "4096.123"}))
            if allow_null:
                return None
            else:
                raise RuntimeError(f'Unexpected call: key={key}, recurse={recurse}')


        kv.kv_get = my_get
        utils.kv = kv
        cdf.utils = utils
        cdf._get_m0d_per_cvg = Mock(return_value=1)
        ret = cdf._create_node_descriptions()
        self.assertEqual('None (P)', str(ret[0].data_iface_type))
