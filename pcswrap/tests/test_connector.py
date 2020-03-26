# flake8: noqa
import sys
sys.path.insert(0, '..')
from unittest.mock import Mock, MagicMock
from pcswrap.client import Client
from pcswrap.exception import PcsNoStatusException
from pcswrap.internal.connector import CliExecutor, CliConnector
import unittest
import os


def contents(filename: str) -> str:
    dirname = os.path.dirname(os.path.realpath(__file__))
    fullpath = f'{dirname}/{filename}'
    assert os.path.isfile(fullpath), f'No such file: {fullpath}'
    with open(fullpath) as f:
        s = f.read()
    return s


GOOD_XML = contents('status-xml-w-clones.xml')
XML_PLAIN_RESOURCES = contents('status-xml-plain-resources.xml')

GOOD_STATUS_TEXT = '''Cluster name: mycluster

WARNINGS:
No stonith devices and stonith-enabled is not false

Stack: corosync
Current DC: ssc-vm-0018 (version 1.1.20-5.el7_7.2-3c4c782f70) - partition with quorum
Last updated: Fri Feb 28 04:25:41 2020
Last change: Fri Feb 28 02:24:06 2020 by hacluster via crmd on ssc-vm-0018

1 node configured
0 resources configured

Online: [ ssc-vm-0018 ]

No resources


Daemon Status:
  corosync: active/disabled
  pacemaker: active/disabled
  pcsd: active/disabled
'''


class PcsExecutorTest(unittest.TestCase):
    def test_get_nodes_works(self):

        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        nodes = connector.get_nodes()
        self.assertEqual(2, len(nodes))

    def test_node_online_parsed_correctly(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        nodes = connector.get_nodes()
        self.assertEqual(2, len(nodes))
        self.assertTrue(nodes[0].online)
        self.assertFalse(nodes[1].online)

    def test_broken_xml_causes_exception(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock(side_effect=['broken'])
        connector = CliConnector(executor=stub_executor)
        with self.assertRaises(PcsNoStatusException):
            connector.get_nodes()

    def test_get_cluster_name_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_status_text = MagicMock(
            side_effect=[GOOD_STATUS_TEXT])
        connector = CliConnector(executor=stub_executor)
        self.assertEqual('mycluster', connector.get_cluster_name())

    def test_get_resources_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock(side_effect=[GOOD_XML])
        connector = CliConnector(executor=stub_executor)
        resources = connector.get_resources()
        self.assertEqual(6, len(resources))

    def test_plain_resources_parsed_also(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock(
            side_effect=[XML_PLAIN_RESOURCES])
        connector = CliConnector(executor=stub_executor)
        resources = connector.get_resources()
        self.assertEqual(3, len(resources))
        self.assertEqual(['c-259.stonith', 'c-260.stonith', 'MyResource'],
                         [x.id for x in resources])

    def test_get_stonith_resources_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock(
            side_effect=[XML_PLAIN_RESOURCES])
        connector = CliConnector(executor=stub_executor)
        resources = connector.get_stonith_resources()
        self.assertEqual(['c-259.stonith', 'c-260.stonith'],
                         [x.id for x in resources])


class ClientTest(unittest.TestCase):
    def test_get_nodes_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        client = Client(connector=connector)

        nodes = client.get_all_nodes()
        self.assertEqual(2, len(nodes))

    def test_get_online_nodes_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        client = Client(connector=connector)

        nodes = client.get_online_nodes()
        self.assertEqual(1, len(nodes))
