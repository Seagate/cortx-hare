import argparse
import json
import os
import sys
from typing import List

from pcswrap.exception import CliException
from pcswrap.internal.connector import CliConnector
from pcswrap.types import Node, PcsConnector


class Client():
    def __init__(self, connector: PcsConnector = None):
        self.connector: PcsConnector = connector or CliConnector()
        self._ensure_sane()

    def _ensure_sane(self) -> None:
        self.connector.get_nodes()

    def get_all_nodes(self) -> List[Node]:
        return self.connector.get_nodes()

    def get_online_nodes(self) -> List[Node]:
        return [x for x in self.connector.get_nodes() if x.online]

    def unstandby_node(self, node_name) -> None:
        self.connector.unstandby_node(node_name)

    def standby_node(self, node_name) -> None:
        self.connector.standby_node(node_name)

    def get_cluster_name(self) -> str:
        return self.connector.get_cluster_name()

    def standby_all(self) -> None:
        self.connector.standby_all()

    def unstandby_all(self) -> None:
        self.connector.unstandby_all()

    def shutdown_node(self, node_name: str) -> None:
        self.connector.shutdown_node(node_name)


def parse_opts(argv: List[str]):
    prog_name = os.environ.get('PCSCLI_PROG_NAME')

    p = argparse.ArgumentParser(
        prog=prog_name,
        description='Manages the nodes in HA cluster.')
    subparsers = p.add_subparsers()
    status_parser = subparsers.add_parser(
        'status',
        help='Show status of all cluster nodes',
    )
    unstandby_parser = subparsers.add_parser('unstandby',
                                             help='Unstandby a node')
    standby_parser = subparsers.add_parser('standby', help='Standby a node')
    shutdown_parser = subparsers.add_parser(
        'shutdown', help='Shutdown (power off) the node by name')

    standby_parser.add_argument('standby_node',
                                type=str,
                                nargs='?',
                                help='Name of the node to standby')
    standby_parser.add_argument(
        '--all',
        action='store_true',
        dest='standby_node_all',
        help='Standby all the nodes in the cluster (no node name is required)')
    unstandby_parser.add_argument('unstandby_node',
                                  type=str,
                                  nargs='?',
                                  help='Name of the node to unstandby')
    unstandby_parser.add_argument(
        '--all',
        action='store_true',
        dest='unstandby_node_all',
        help='Unstandby all the nodes in the cluster '
        '(no node name is required)')
    status_parser.add_argument('--stub',
                               dest='show_status',
                               default=True,
                               help=argparse.SUPPRESS)
    shutdown_parser.add_argument('shutdown_node',
                                 type=str,
                                 nargs=1,
                                 help='Name of the node to poweroff')
    opts = p.parse_args(argv)
    return opts


def _get_client() -> Client:
    return Client()


def _run(args) -> None:
    if hasattr(args, 'standby_node'):
        if hasattr(args, 'standby_node_all'):
            _get_client().standby_all()
        else:
            _get_client().standby_node(args.standby_node)
    elif hasattr(args, 'unstandby_node'):
        if hasattr(args, 'unstandby_node_all'):
            _get_client().unstandby_all()
        else:
            _get_client().unstandby_node(args.stop_node)
    elif hasattr(args, 'show_status'):
        nodes = [node._asdict() for node in _get_client().get_all_nodes()]
        json_str = json.dumps(nodes)
        print(json_str)
    elif hasattr(args, 'shutdown_node'):
        node = args.shutdown_node[0]
        _get_client().shutdown_node(node)


def main() -> None:
    args = parse_opts(sys.argv[1:])
    try:
        _run(args)
    except CliException as e:
        print(e.err, file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Unexpected error:', sys.exc_info()[0], file=sys.stderr)
        sys.exit(1)
