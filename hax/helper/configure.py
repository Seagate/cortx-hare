# Copyright (c) 2021 Seagate Technology LLC and/or its Affiliates
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

import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

import click

from helper.exec import CliException, Executor, Program, two_columns


@dataclass
class AppCtx:
    """
    A storage for application context.
    Conains the parameters to run the current application.
    """
    cdf_path: str
    conf_dir: str


def _setup_logging():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s [%(levelname)s] %(message)s')


@click.command()
@click.argument('cdf', type=click.Path(exists=True), required=True)
@click.option('--conf-dir',
              '-c',
              type=str,
              default='/var/lib/hare/',
              help='Target folder where Hare-related configuration will '
              'be written to.',
              show_default=True)
@click.pass_context
def parse_opts(ctx, cdf: str, conf_dir: str):
    """Generate Hare configuration according to the given CDF file.

    CDF   Full path to the Cluster Description File (CDF)."""
    ctx.ensure_object(dict)
    ctx.obj['result'] = AppCtx(cdf_path=cdf, conf_dir=conf_dir)
    return ctx.obj


class ConfGenerator:
    def __init__(self, cdf_path: str, conf_dir: str):
        self.cdf_path = cdf_path
        self.conf_dir = conf_dir
        self.executor = Executor()

    def generate(self) -> None:
        p = Program
        executor = self.executor
        conf_dir = self.conf_dir

        env = self._get_pythonic_env()
        executor.run(p(['cfgen', '-o', self.conf_dir, self.cdf_path]), env=env)
        xcode = executor.run(p(['cat', f'{conf_dir}/confd.dhall'])
                             | p(['dhall', 'text'])
                             | p(['m0confgen']),
                             env=env)
        self._write_file(f'{conf_dir}/confd.xc', xcode)

        node_name = self._create_node_name(f'{conf_dir}/consul-agents.json')
        self._update_consul_conf(node_name)

    def _get_pythonic_env(self) -> Dict[str, str]:
        path = os.environ['PATH']

        # Make sure that cfgen will be able to import the same modules
        # that the current script can
        py_path = ':'.join(sys.path)
        if 'PYTHONPATH' in os.environ:
            env_var = os.environ['PYTHONPATH']
            py_path = f'{env_var}:{py_path}'
        env = {
            'PATH':
            ':'.join([
                '/opt/seagate/cortx/hare/bin',
                '/opt/seagate/cortx/hare/libexec', path
            ]),
            'PYTHONPATH':
            py_path
        }
        return env

    def _write_file(self, path: str, contents: str):
        with open(path, 'w') as f:
            f.write(contents)

    def _read_file(self, path: str) -> str:
        with open(path, 'r') as f:
            return f.read()

    def _update_consul_conf(self, node_name) -> None:
        cns_file = f'{self.conf_dir}/consul-agents.json'

        def get_join_ip() -> str:
            for node, ip in self._get_server_nodes(cns_file):
                if node == node_name:
                    return ip
            raise RuntimeError(f'Logic error: node_name={node_name}'
                               f' not found in {cns_file}')

        join_ip = get_join_ip()
        join_peers_opt: List[str] = []
        for node, ip in self._get_server_nodes(cns_file):
            if node == node_name:
                continue
            join_peers_opt += ['--join', ip]

        self.executor.run(Program([
            'mk-consul-env', '--mode', 'server', '--bind', join_ip,
            *join_peers_opt, '--extra-options', '-ui -bootstrap-expect 1',
            '--conf-dir', f'{self.conf_dir}'
        ]),
                          env=self._get_pythonic_env())

        self.executor.run(Program([
            'update-consul-conf', '--conf-dir', f'{self.conf_dir}',
            '--kv-file', f'{self.conf_dir}/consul-kv.json'
        ]),
                          env=self._get_pythonic_env())

    def _create_node_name(self, consul_agents_file: str) -> str:
        path = f'{self.conf_dir}/node-name'
        for node, _ in self._get_nodes(consul_agents_file):
            if self._is_localhost(node):
                logging.debug('Writing %s to file %s', node, path)
                self._write_file(path, node)
                return node
        raise RuntimeError('Failed to find the current node inthe node list')

    def _is_localhost(self, hostname: str) -> bool:
        runner = self.executor
        p = Program
        if hostname in ('localhost', '127.0.0.1'):
            return True
        if hostname == runner.run(p(['hostname'])):
            return True
        if hostname == runner.run(p(['hostname', '--fqdn'])):
            return True

        all_ips = runner.run(p(['hostname', '-I']))
        if all_ips.find(hostname) > -1:
            return True

        minion_file = '/etc/salt/minion_id'
        if not os.path.exists(minion_file):
            return False

        return hostname == self._read_file(minion_file).strip()

    def _get_server_nodes(self,
                          consul_agents_file: str) -> List[Tuple[str, str]]:
        return self._get_nodes_ex(consul_agents_file,
                                  '.servers[] | "\\(.node_name) \\(.ipaddr)"')

    def _get_nodes(self, consul_agents_file: str) -> List[Tuple[str, str]]:
        return self._get_nodes_ex(
            consul_agents_file,
            '(.servers + .clients)[] | "\\(.node_name) \\(.ipaddr)"')

    def _get_nodes_ex(self, consul_agents_file: str,
                      jq_selector: str) -> List[Tuple[str, str]]:
        executor = self.executor

        return executor.run_ex(
            Program(['jq', '-r', jq_selector, consul_agents_file]),
            two_columns)


def main():
    _setup_logging()
    try:
        raw_ctx = parse_opts(args=sys.argv[1:], standalone_mode=False, obj={})
        if not isinstance(raw_ctx, dict):
            # --help was invoked
            sys.exit(1)
        app_context = raw_ctx['result']
        ConfGenerator(app_context.cdf_path, app_context.conf_dir).generate()
    except CliException as e:
        logging.error('Exiting due to a failure: %s', e)
        logging.debug('Failed command: %s', e.cmd)
        logging.debug('Environment: %s', e.env)
        sys.exit(e.code)
    except Exception as e:
        logging.error('Exiting due to a failure: %s', e)
        logging.debug('Details on the error:', exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
