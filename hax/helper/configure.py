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
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Tuple

import click
from hax.log import create_logger_directory

from helper.exec import CliException, Executor, Program, two_columns


@dataclass
class AppCtx:
    """
    A storage for application context.
    Conains the parameters to run the current application.
    """
    cdf_path: str
    conf_dir: str
    log_dir: str
    log_file: str
    consul_server: bool
    uuid: str
    transport: str


def _setup_logging(opts: AppCtx):
    log_dir = opts.log_dir
    max_size = 1024 * 1024
    handlers: List[logging.Handler] = [StreamHandler(stream=sys.stderr)]
    if log_dir:
        filename = opts.log_file
        log_file = f'{log_dir}/{filename}'
        create_logger_directory(log_dir)
        handlers.append(
            RotatingFileHandler(log_file,
                                maxBytes=max_size,
                                mode='a',
                                backupCount=5,
                                encoding=None,
                                delay=False))

    logging.basicConfig(level=logging.INFO,
                        handlers=handlers,
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
@click.option('--transport',
              '-t',
              type=str,
              default='libfab',
              help='Transport type to be used, '
              'presently supported are lnet and libfabric',
              show_default=True)
@click.option('--log-dir',
              '-l',
              type=str,
              default='/var/log/seagate/hare',
              help='Target folder where log files needs to be generated',
              show_default=True)
@click.option('--consul-server',
              '-s',
              is_flag=True,
              help='Configure given node as a consul server.')
@click.option('--uuid', type=str, help='UUID to be used', show_default=True)
@click.option('--log-file',
              type=str,
              default='setup.log',
              help='File name of the log file.',
              show_default=True)
@click.pass_context
def parse_opts(ctx, cdf: str, conf_dir: str, transport: str, log_dir: str,
               consul_server: bool, uuid: str, log_file: str):
    """Generate Hare configuration according to the given CDF file.

    CDF   Full path to the Cluster Description File (CDF)."""
    ctx.ensure_object(dict)
    ctx.obj['result'] = AppCtx(cdf_path=cdf,
                               conf_dir=conf_dir,
                               transport=transport,
                               log_dir=log_dir,
                               consul_server=consul_server,
                               uuid=uuid,
                               log_file=log_file)
    return ctx.obj


class ConfGenerator:
    def __init__(self, context: AppCtx):
        self.cdf_path = context.cdf_path
        self.conf_dir = context.conf_dir
        self.transport = context.transport
        self.log_dir = context.log_dir
        self.consul_server = context.consul_server
        self.uuid = context.uuid
        self.log_file = context.log_file
        self.executor = Executor()

    def generate(self) -> None:
        p = Program
        executor = self.executor
        conf_dir = self.conf_dir

        env = self._get_pythonic_env()
        executor.run(p([
            'cfgen', '-o', self.conf_dir, '-v', '-l', self.log_dir,
            '--log-file', self.log_file, self.cdf_path
        ]),
                     env=env)
        xcode = executor.run(p(['cat', f'{conf_dir}/confd.dhall'])
                             | p(['dhall', 'text'])
                             | p(['m0confgen']),
                             env=env)
        self._write_file(f'{conf_dir}/confd.xc', xcode)

        node_name = self._create_node_name(f'{conf_dir}/consul-agents.json')
        self._update_consul_conf(node_name, self.transport)

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

    def _update_consul_conf(self, node_name, transport: str) -> None:
        cns_file = f'{self.conf_dir}/consul-agents.json'

        def get_join_ip() -> str:
            for node, ip in self._get_nodes(cns_file):
                if node == node_name:
                    return ip
            raise RuntimeError(f'Logic error: node_name={node_name}'
                               f' not found in {cns_file}')

        join_ip = get_join_ip()
        join_peers_opt: List[str] = []
        for node, ip in self._get_data_nodes(cns_file):
            if node == node_name:
                continue
            join_peers_opt += ['--join', ip]

        mk_consul_env_cmd = [
            'mk-consul-env', '--bind', join_ip, *join_peers_opt,
            '--extra-options', '-ui -bootstrap-expect 1', '--conf-dir',
            f'{self.conf_dir}'
        ]
        if self.consul_server:
            mk_consul_env_cmd.extend(['--mode', 'server'])
        else:
            mk_consul_env_cmd.extend(['--mode', 'client'])

        self.executor.run(Program(mk_consul_env_cmd),
                          env=self._get_pythonic_env())

        update_consul_conf_cmd = [
            'update-consul-conf', '--conf-dir', f'{self.conf_dir}',
            '--xprt', f'{transport}',
            '--kv-file', f'{self.conf_dir}/consul-kv.json', '--log-dir',
            self.log_dir
        ]

        if self.consul_server:
            update_consul_conf_cmd.append('--server')

        if self.uuid:
            update_consul_conf_cmd.extend(['--uuid', self.uuid])

        self.executor.run(Program(update_consul_conf_cmd),
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

    def _get_data_nodes(self,
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
    try:
        raw_ctx = parse_opts(args=sys.argv[1:], standalone_mode=False, obj={})
        if not isinstance(raw_ctx, dict):
            # --help was invoked
            sys.exit(1)
        app_context = raw_ctx['result']
        _setup_logging(app_context)
        ConfGenerator(app_context).generate()
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
