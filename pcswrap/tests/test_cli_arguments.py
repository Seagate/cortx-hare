# flake8: noqa: E401
import sys
sys.path.insert(0, '..')
from unittest.mock import MagicMock, call
from pcswrap.client import Client, AppRunner
from pcswrap.internal.connector import CliExecutor, CliConnector
from typing import Tuple
import unittest
import os
import inspect


def contents(filename: str) -> str:
    dirname = os.path.dirname(os.path.realpath(__file__))
    fullpath = f'{dirname}/{filename}'
    assert os.path.isfile(fullpath), f'No such file: {fullpath}'
    with open(fullpath) as f:
        s = f.read()
    return s


def mock_methods(obj):
    # [KN] By some reason there is no clean way to make all public methods
    # mocked just by default. But in test we are usually interested in the
    # certain methods only, if other ones are invoked,
    # this should mean FAILURE.

    assert obj is not None
    members = inspect.getmembers(obj)
    func_names = [
        name for (name, val) in members
        if not name.startswith('_') and inspect.ismethod(val)
    ]

    for n in func_names:
        setattr(
            obj, n,
            MagicMock(
                side_effect=Exception(f'Unexpected invocation: function {n}')))
    return obj


GOOD_XML = contents('status-xml-w-clones.xml')
XML_PLAIN_RESOURCES = contents('status-xml-plain-resources.xml')


class AppRunnerTest(unittest.TestCase):
    def _create_client_and_runner(self) -> Tuple[Client, AppRunner]:
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        stub_client = Client(connector=connector)
        stub_client = mock_methods(stub_client)

        runner = AppRunner()
        runner._get_client = lambda x: stub_client
        return (stub_client, runner)

    def test_status_works(self):
        stub_client, runner = self._create_client_and_runner()

        # Note that any method except for get_all_nodes will raise an
        # exception immediately.
        stub_client.get_all_nodes = MagicMock()

        runner.run(['status'])
        self.assertTrue(stub_client.get_all_nodes.called)

    def test_standby_single_node_works(self):
        stub_client, runner = self._create_client_and_runner()
        stub_client.standby_node = MagicMock()

        runner.run(['standby', 'mynode'])
        self.assertTrue(stub_client.standby_node.called)
        self.assertEqual([call('mynode')],
                         stub_client.standby_node.call_args_list)

    def test_standby_all_works(self):
        stub_client, runner = self._create_client_and_runner()
        stub_client.standby_all = MagicMock()
        runner.run(['standby', '--all'])
        self.assertTrue(stub_client.standby_all.called)

    def test_unstandby_single_node_works(self):
        stub_client, runner = self._create_client_and_runner()
        stub_client.unstandby_node = MagicMock()

        runner.run(['unstandby', 'mynode'])
        self.assertTrue(stub_client.unstandby_node.called)
        self.assertEqual([call('mynode')],
                         stub_client.unstandby_node.call_args_list)

    def test_unstandby_all_works(self):
        stub_client, runner = self._create_client_and_runner()
        stub_client.unstandby_all = MagicMock()
        runner.run(['unstandby', '--all'])
        self.assertTrue(stub_client.unstandby_all.called)

    def test_maintenance_all_works(self):
        stub_client, runner = self._create_client_and_runner()
        stub_client.cluster_maintenance = MagicMock()

        runner.run(['maintenance', '--all'])
        self.assertTrue(stub_client.cluster_maintenance.called)

    def test_unmaintenance_all_works(self):
        stub_client, runner = self._create_client_and_runner()
        stub_client.cluster_unmaintenance = MagicMock()

        runner.run(['unmaintenance', '--all'])
        self.assertTrue(stub_client.cluster_unmaintenance.called)

    def test_shutdown_node_works(self):
        stub_client, runner = self._create_client_and_runner()
        stub_client.shutdown_node = MagicMock()

        runner.run(['shutdown', 'node01'])
        self.assertTrue(stub_client.shutdown_node.called)
        self.assertEqual([call('node01', timeout=120)],
                         stub_client.shutdown_node.call_args_list)
