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

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Any, Callable
from sys import exit

import yaml
from cortx.utils.product_features import unsupported_features

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider
from hare_mp.validator import Validator


def execute(cmd: List[str]) -> str:
    process = subprocess.Popen(cmd,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               encoding='utf8')
    out, err = process.communicate()
    if process.returncode:
        raise Exception(
            f'Command {cmd} exited with error code {process.returncode}. '
            f'Command output: {err}')

    return out


def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(message)s')


def get_data_from_provisioner_cli(method, output_format='json') -> str:
    try:
        process = subprocess.run(
            ['provisioner', method, f'--out={output_format}'],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False)
        stdout = process.stdout
        rc = process.returncode
    except Exception as e:
        logging.error('Failed to fetch data from provisioner (%s)', e)
        return 'unknown'
    if rc != 0:
        return 'unknown'
    res = stdout.decode('utf-8')
    return json.loads(res)['ret'] if res else 'unknown'


def _report_unsupported_features(features_unavailable):
    uf_db = unsupported_features.UnsupportedFeaturesDB()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        uf_db.store_unsupported_features('hare', features_unavailable))


def logrotate():
    try:
        setup_info = get_data_from_provisioner_cli('get_setup_info')
        if setup_info != 'unknown':
            server_type = setup_info['server_type']
            shutil.copyfile(
                f'/opt/seagate/cortx/hare/conf/logrotate/{server_type}',
                '/etc/logrotate.d/hare')
    except Exception as error:
        logging.error('Cannot configure logrotate for hare (%s)', error)


def unsupported_feature():
    try:
        features_unavailable = []
        path = '/opt/seagate/cortx/hare/conf/setup_info.json'
        with open(path) as hare_features_info:
            hare_unavailable_features = json.load(hare_features_info)
            setup_info = get_data_from_provisioner_cli('get_setup_info')
            if setup_info != 'unknown':
                for setup in hare_unavailable_features['setup_types']:
                    if setup['server_type'] == setup_info['server_type']:
                        features_unavailable.extend(
                            setup['unsupported_features'])
                        _report_unsupported_features(features_unavailable)
    except Exception as error:
        logging.error('Error reporting hare unsupported features (%s)', error)


def post_install(args):
    try:
        if checkRpm('cortx-motr') != 0:
            logging.error('\'cortx-motr\' is not installed')
            exit(-1)
        if checkRpm('consul') != 0:
            logging.error('\'consul\' is not installed')
            exit(-1)
        if checkRpm('cortx-hare') != 0:
            logging.error('\'cortx-hare\' is not installed')
            exit(-1)
        if checkRpm('cortx-py-utils') != 0:
            logging.error('\'cortx-py-utils\' is not installed')
            exit(-1)
        if checkRpm('cortx-s3server') != 0:
            logging.warning('\'cortx-s3server\' is not installed')

        if args.report_unavailable_features:
            unsupported_feature()

        if args.configure_logrotate:
            logrotate()

    except Exception as error:
        logging.error('Error while checking installed rpms (%s)', error)
        exit(-1)


def init(args):
    try:
        rc = 0
        url = args.config[0]
        validator = Validator(ConfStoreProvider(url))
        if validator.is_first_node_in_cluster():
            path_to_cdf = args.file[0]
            if not is_cluster_running() and bootstrap_cluster(path_to_cdf):
                logging.error('Failed to bootstrap the custer')
                rc = -1
            shutdown_cluster()
        exit(rc)
    except Exception as error:
        logging.error('Error while initializing the cluster (%s)', error)
        shutdown_cluster()
        exit(-1)


def test(args):
    try:
        rc = 0
        url = args.config[0]
        validator = Validator(ConfStoreProvider(url))
        if validator.is_first_node_in_cluster():
            path_to_cdf = args.file[0]
            if not is_cluster_running() and bootstrap_cluster(path_to_cdf):
                logging.error('Failed to bootstrap the cluster')
                rc = -1
            cluster_status = check_cluster_status(path_to_cdf)
            shutdown_cluster()
            if cluster_status:
                logging.error('Cluster status reports failure')
                rc = -1
        exit(rc)
    except Exception as error:
        logging.error('Error while checking cluster status (%s)', error)
        shutdown_cluster()
        exit(-1)


def generate_support_bundle(args):
    try:
        # Default target directory is /tmp/hare
        if os.system('hctl reportbug') != 0:
            logging.error('Failed to generate support bundle')
            exit(-1)
    except Exception as error:
        logging.error('Error while generating support bundle (%s)', error)
        exit(-1)


def noop(args):
    exit(0)


def checkRpm(rpm_name):
    rpm_list = subprocess.Popen(["rpm", "-qa"],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env={},
                                encoding='utf8')
    rpm_search = subprocess.Popen(["grep", "-q", rpm_name],
                                  stdin=rpm_list.stdout,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  env={},
                                  encoding='utf8')
    out, err = rpm_search.communicate()
    logging.debug("Output: {}".format(out))
    logging.debug("stderr: {}".format(err))

    return rpm_search.returncode


def is_cluster_running() -> bool:
    return os.system('hctl status >/dev/null') == 0


def bootstrap_cluster(path_to_cdf: str):
    return os.system('hctl bootstrap --mkfs ' + path_to_cdf)


def shutdown_cluster():
    while is_cluster_running():
        os.system('hctl shutdown')


def list2dict(
        nodes_data_hctl: List[Dict[str,
                                   Any]]) -> Dict[str, Dict[str, List[str]]]:
    node_info_dict = {}
    for node in nodes_data_hctl:
        node_svc_info: Dict[str, List[str]] = {}
        for service in node['svcs']:
            if not service['name'] in node_svc_info.keys():
                node_svc_info[service['name']] = []
            if (service['status'] == 'started'):
                node_svc_info[service['name']].append(service['status'])
        node_info_dict[node['name']] = node_svc_info

    return node_info_dict


def check_cluster_status(path_to_cdf: str):
    cluster_desc = None
    with open(path_to_cdf, 'r') as stream:
        cluster_desc = yaml.safe_load(stream)
    cmd = ['hctl', 'status', '--json']
    cluster_info = json.loads(execute(cmd))
    nodes_data_hctl = cluster_info['nodes']

    node_info_dict = list2dict(nodes_data_hctl)
    for node in cluster_desc['nodes']:
        s3_cnt = int(node['m0_clients']['s3'])
        m0ds = node.get('m0_servers', [])
        ios_cnt = 0
        for m0d in m0ds:
            if 'runs_confd' in m0d.keys(
            ) and node_info_dict[node['hostname']]['confd'][0] != 'started':
                return -1
            if m0d['io_disks']['data']:
                if node_info_dict[
                        node['hostname']]['ioservice'][ios_cnt] != 'started':
                    return -1
                ios_cnt += 1
        if s3_cnt and len(
                node_info_dict[node['hostname']]['s3server']) != s3_cnt:
            return -1

    return 0


def generate_cdf(url: str) -> str:
    generator = CdfGenerator(ConfStoreProvider(url))
    return generator.generate()


def save(filename: str, contents: str) -> None:
    with open(filename, 'w') as f:
        f.write(contents)


def config(args):
    try:
        url = args.config[0]
        filename = args.file[0] or '/var/lib/hare/cluster.yaml'
        save(filename, generate_cdf(url))
    except Exception as error:
        logging.error('Error performing configuration (%s)', error)
        exit(-1)


def add_subcommand(subparser, command: str, help_str: str,
                   handler_fn: Callable[[Any], None]):
    parser = subparser.add_parser(command, help=help_str)
    parser.set_defaults(func=handler_fn)
    parser.add_argument('--config',
                        help='Conf Store URL with cluster info',
                        required=True,
                        nargs=1,
                        type=str,
                        action='store')
    return parser


def add_file_argument(parser):
    parser.add_argument('--file',
                        help='Full path to the CDF file.',
                        nargs=1,
                        default=['/var/lib/hare/cluster.yaml'],
                        type=str,
                        action='store')
    return parser


def main():
    p = argparse.ArgumentParser(description='Configure hare settings')
    subparser = p.add_subparsers()

    parser = add_subcommand(subparser,
                            'post_install',
                            help_str='Perform post installation checks',
                            handler_fn=post_install)
    parser.add_argument(
        '--report-unavailable-features',
        help='Report unsupported features according to setup type',
        action='store_true')
    parser.add_argument('--configure-logrotate',
                        help='Configure logrotate for hare',
                        action='store_true')

    add_file_argument(
        add_subcommand(subparser,
                       'config',
                       help_str='Configure Hare',
                       handler_fn=config))

    add_file_argument(
        add_subcommand(subparser,
                       'init',
                       help_str='Perform component initialization',
                       handler_fn=init))

    add_file_argument(
        add_subcommand(subparser,
                       'test',
                       help_str='Testing cluster status',
                       handler_fn=test))

    add_subcommand(subparser,
                   'support_bundle',
                   help_str='Generating support bundle',
                   handler_fn=generate_support_bundle)
    add_subcommand(subparser,
                   'reset',
                   help_str='Reset/cleanup step',
                   handler_fn=noop)
    add_subcommand(subparser,
                   'cleanup',
                   help_str='Reset/cleanup step',
                   handler_fn=noop)

    add_subcommand(subparser,
                   'prepare',
                   help_str='Prepare step',
                   handler_fn=noop)
    setup_logging()

    parsed = p.parse_args(sys.argv[1:])

    if not hasattr(parsed, 'func'):
        logging.error('Error: No valid command passed. Please check "--help"')
        exit(1)

    parsed.func(parsed)


if __name__ == '__main__':
    main()
