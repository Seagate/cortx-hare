# flake8: noqa
import unittest
from typing import Any
from unittest.mock import MagicMock, Mock

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ValueProvider
from hare_mp.types import (DisksDesc, DList, M0Clients, M0ServerDesc, Maybe,
                           NodeDesc, Protocol, Text)


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
        self.assertEqual('Some P.tcp', str(Maybe(Protocol.tcp, 'P')))

    def test_disks_empty(self):
        val = M0ServerDesc(runs_confd=Maybe(True, 'Bool'),
                           io_disks=DisksDesc(meta_data=Maybe(None, 'Text'),
                                              data=DList([], 'List Text')))
        self.assertEqual(
            '{ runs_confd = Some True, io_disks = { meta_data = None Text, data = [] : List Text } }',
            str(val))

    def test_m0server_with_disks(self):
        val = M0ServerDesc(
            runs_confd=Maybe(True, 'Bool'),
            io_disks=DisksDesc(
                meta_data=Maybe(None, 'Text'),
                data=DList([Text('/disk1'), Text('/disk2')], 'test')))
        self.assertEqual(
            '{ runs_confd = Some True, io_disks = { meta_data = None Text, data = ["/disk1", "/disk2"] } }',
            str(val))


class TestCDF(unittest.TestCase):
    def test_it_works(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1"
                },
                'cluster>srvnode_1>hostname': 'myhost',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>network>data>public_interfaces': ['eth1', 'eno2']
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
                'cluster>srvnode_1>hostname': 'myhost',
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_1>network>data>public_interfaces': ['eth1', 'eno2']
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(1, len(ret))
        self.assertEqual(Text('myhost'), ret[0].hostname)
        self.assertEqual(Text('eth1'), ret[0].data_iface)

    def test_multiple_nodes_supported(self):
        store = ValueProvider()

        def ret_values(value: str) -> Any:
            data = {
                'cluster>server_nodes': {
                    "blah": "srvnode_1",
                    "zweite": "srvnode_2"
                },
                'cluster>srvnode_1>hostname': 'myhost',
                'cluster>srvnode_1>network>data>public_interfaces': ['eth1', 'eno2'],
                'cluster>srvnode_1>storage>data_devices': ['/dev/sdb'],
                'cluster>srvnode_2>hostname': 'host-2',
                'cluster>srvnode_2>network>data>public_interfaces': ['eno1'],
                'cluster>srvnode_2>storage>data_devices': ['/dev/sdb']
            }
            return data[value]

        store._raw_get = Mock(side_effect=ret_values)

        ret = CdfGenerator(provider=store)._create_node_descriptions()
        self.assertIsInstance(ret, list)
        self.assertEqual(2, len(ret))
        self.assertEqual(Text('myhost'), ret[0].hostname)
        self.assertEqual(Text('eth1'), ret[0].data_iface)
        self.assertEqual(Text('host-2'), ret[1].hostname)
        self.assertEqual(Text('eno1'), ret[1].data_iface)
