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
from enum import Enum
from sys import exit
from time import sleep
from typing import Any, Callable, Dict, List
from datetime import datetime

import yaml
from cortx.utils.product_features import unsupported_features
from hax.types import KeyDelete
from hax.util import ConsulUtil, repeat_if_fails, KVAdapter

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider
from hare_mp.systemd import HaxUnitTransformer
from hare_mp.validator import Validator

# Logger details
LOG_DIR = "/var/log/seagate/hare/"
LOG_FILE = "/var/log/seagate/hare/setup.log"
LOG_FILE_SIZE = 5 * 1024 * 1024


class Plan(Enum):
    Sanity = 'sanity'
    Regression = 'regression'
    Full = 'full'
    Performance = 'performance'
    Scalability = 'scalability'


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


def create_logger_directory():
    """Create log directory if not exists."""
    if not os.path.isdir(LOG_DIR):
        try:
            os.makedirs(LOG_DIR)
        except Exception:
            logging.exception(f"{LOG_DIR} Could not be created")
            shutdown_cluster()
            exit(-1)


def setup_logging() -> None:
    console = logging.StreamHandler(stream=sys.stderr)
    fhandler = logging.handlers.RotatingFileHandler(LOG_FILE,
                                                    maxBytes=LOG_FILE_SIZE,
                                                    mode='a',
                                                    backupCount=5,
                                                    encoding=None,
                                                    delay=False)
    logging.basicConfig(level=logging.INFO,
                        handlers=[console, fhandler],
                        format='%(asctime)s [%(levelname)s] %(message)s')


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


def get_server_type(url: str) -> str:
    try:
        provider = ConfStoreProvider(url)
        machine_id = provider.get_machine_id()
        server_type = provider.get(f'server_node>{machine_id}>type')

        if server_type == 'VM':
            return 'virtual'
        else:
            return 'physical'
    except Exception as error:
        logging.error('Cannot get server type (%s)', error)
        return 'unknown'


def logrotate(url: str):
    try:
        server_type = get_server_type(url)
        logging.info('Server type (%s)', server_type)

        if server_type != 'unknown':
            shutil.copyfile(
                f'/opt/seagate/cortx/hare/conf/logrotate/{server_type}',
                '/etc/logrotate.d/hare')
    except Exception as error:
        logging.error('Cannot configure logrotate for hare (%s)', error)


def unsupported_feature(url: str):
    try:
        features_unavailable = []
        path = '/opt/seagate/cortx/hare/conf/setup_info.json'
        with open(path) as hare_features_info:
            hare_unavailable_features = json.load(hare_features_info)

            server_type = get_server_type(url)
            logging.info('Server type (%s)', server_type)

            if server_type != 'unknown':
                for setup in hare_unavailable_features['setup_types']:
                    if setup['server_type'] == server_type:
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
            unsupported_feature(args.config[0])

        if args.configure_logrotate:
            logrotate(args.config[0])

    except Exception as error:
        logging.error('Error while checking installed rpms (%s)', error)
        exit(-1)


def enable_hare_consul_agent() -> None:
    cmd = ['systemctl', 'enable', 'hare-consul-agent']
    execute(cmd)


def disable_hare_consul_agent() -> None:
    cmd = ['systemctl', 'disable', 'hare-consul-agent']
    execute(cmd)


def init(args):
    try:
        rc = 0
        url = args.config[0]
        validator = Validator(ConfStoreProvider(url))
        disable_hare_consul_agent()
        if validator.is_first_node_in_cluster():
            path_to_cdf = args.file[0]
            if not is_cluster_running() and bootstrap_cluster(
                    path_to_cdf, True):
                logging.error('Failed to bootstrap the cluster')
                rc = -1
            if rc == 0:
                wait_for_cluster_start(url)
            shutdown_cluster()
        enable_hare_consul_agent()
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
            if rc == 0:
                wait_for_cluster_start(url)
            shutdown_cluster()
            if cluster_status:
                logging.error('Cluster status reports failure')
                rc = -1
        exit(rc)
    except Exception as error:
        logging.error('Error while checking cluster status (%s)', error)
        shutdown_cluster()
        exit(-1)


def executecmds(cmd: List[str]) -> list:
    process = subprocess.Popen(cmd,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               encoding='utf8')
    resp = list(process.communicate())
    resp.append(str(process.returncode))

    return resp


def test_hare_prereq():
    """Test suite for setting the test environment before start of test."""
    pcs_status = ['pcs', 'status']
    cluster_stop = ['cortx', 'cluster', 'stop']

    logging.info('Test started on Host: {}'.format(executecmds(['hostname'])))
    logging.info('Check that all services are up in PCS.')

    resp = executecmds(pcs_status)
    logging.info('PCS status: %s', resp[0])

    if 'cluster is not currently' in resp[0]:
        return

    logging.info('Make Node ready for testing, by stopping the cluster')
    resp = executecmds(cluster_stop)
    if int(resp[2]):
        logging.info('Cluster status : %s', resp[0])
        logging.error('Cluster failed to stop %s', resp[1])
        raise Exception(
            f'Command {cluster_stop} exited with error code '
            f'{int(resp[2])}. Command output: {resp[1]}')
    else:
        logging.info('Cluster Stopped : %s', resp[0])
        for line in resp[0]:
            assert 'Cluster stop is in progress' not in line, \
                'Cluster is in progress.' if 'Cluster is in progress.' \
                else line

def test_hare_postreq(cdf_file: str, timeinfo: str, logfile: str):
    """Test suite is for restoring the setting after test."""
    pcs_status = ['pcs', 'status']
    cluster_start = ['cortx', 'cluster', 'start']
    hctl_status = ['hctl', 'status', '-d']

    logging.info('Start the Cluster')
    resp = executecmds(cluster_start)
    logging.info('cluster status: %s', resp[0])
    if int(resp[2]):
        logging.error('Cluster failed to start %s', resp[1])
        resp = executecmds(['journalctl', '--since', timeinfo, '>', logfile])
        logging.info('created journal log %s', logfile)
        raise Exception(
            f'Command {cluster_start} exited with error code {int(resp[2])}'
            f'Command output: {resp[1]}')
    else:
        for line in resp[0]:
            assert 'Cluster start operation performed' not in line, \
                'Cluster not yet started.' if 'Cluster not yet started.' \
                else line

    cluster_sts = check_cluster_status(cdf_file)
    if cluster_sts:
        logging.error('Cluster status reports failure')
        resp = executecmds(['journalctl', '--since', timeinfo, '>', logfile])
        logging.info('created journal log.%s', logfile)
        exit(-1)

    logging.info('PCS: Check all services are up.')
    sleep(20)
    resp = executecmds(pcs_status)
    logging.info('PCS status: %s', resp[0])
    if int(resp[2]):
        logging.error('PCS failed to updated the status %s', resp[1])
    else:
        for line in resp[0]:
            assert 'stopped' not in line, 'Some services are not up.' \
                if 'Some services are not up.' else line

    logging.info('hctl: Check that all the services are up.')
    sleep(10)
    resp = executecmds(hctl_status)
    logging.info('hctl status: %s', resp[0])
    if int(resp[2]):
        logging.error('hctl failed to updated the status %s', resp[1])
        resp = executecmds(['journalctl', '--since', timeinfo, '>', logfile])
        logging.info('created journal log.%s', logfile)
        raise Exception(
            f'Command {hctl_status} exited with error code {int(resp[2])}.'
            f'Command output: {resp[1]}')
    else:
        for line in resp[0]:
            assert 'stopped' not in line, 'Some services are not up.' \
                if 'Some services are not up.' else line
    logging.info('Successfully performed cleanup after testing')


# @pytest.mark.sanity
def test_hare_bootstrap_shutdown(args):
    """Test suite for single node hare init in loop."""
    loop_count = int(args.dev[0])
    hctl_status = ['hctl', 'status', '-d']
    hctl_shutdown = ['hctl', 'shutdown']

    test_hare_prereq()

    resp = executecmds(hctl_status)
    logging.info('hctl status: %s', resp[0])
    if int(resp[2]):
        logging.error('hctl failed to updated the status %s', resp[1])
        raise Exception(
            f'Command {hctl_status} exited with error code {int(resp[2])}.'
            f'Command output: {resp[1]}')
    else:
        if 'Cluster is not running' not in resp[0]:
            resp = executecmds(hctl_shutdown)
            logging.info('hctl shutdown: %s', resp[0])

        logging.info('-------Starting BOOTSTRAP-SHUTDOWN in LOOP-------')
        for count in range(loop_count):
            logging.info('Loop count# {}'.format(count + 1))
            now = datetime.now()     # current date and time
            date_time = now.strftime("%Y-%m-%d %H:%M:%S")
            jlog = '~/journal_ctrl_' + now.strftime('%Y_%m_%d_%H%M%S') + '.log'

            logging.info('Start hctl Bootstrap')
            resp = bootstrap_cluster(str(args.file[0]), True)
            if resp:
                logging.error('Failed to bootstrap')
                resp = executecmds(['journalctl', '--since', date_time, '>',
                                    jlog])
                logging.info('created journal log %s', jlog)
                exit(-1)

            logging.info('Check that all the services are up in hctl.')
            if is_cluster_running():
                logging.info('hctl is running.')
            else:
                logging.error('Still hctl is not running.')
                resp = executecmds(['journalctl', '--since', date_time, '>',
                                    jlog])
                logging.info('created journal log %s', jlog)
                exit(-1)

            sleep(10)
            logging.info('Shutdown the cluster.')
            resp = executecmds(hctl_shutdown)
            logging.info('hctl shutdown: %s', resp[0])
            if int(resp[2]):
                logging.error('Shutdown Failed %s', resp[1])
                resp = executecmds(
                    ['journalctl', '--since', date_time, '>', jlog])
                logging.info('created journal log.%s', jlog)
                raise Exception(
                    f'Command {hctl_shutdown} exited with error code '
                    f'{int(resp[2])}. Command output: {resp[1]}')

            sleep(10)
            if is_cluster_running():
                logging.error('Still Cluster is running.')
                resp = executecmds(['journalctl', '--since', date_time, '>',
                                    jlog])
                logging.info('created journal log %s', jlog)
                exit(-1)

    test_hare_postreq(str(args.file[0]), date_time, jlog)


def test_IVT(args):
    try:
        rc = 0
        path_to_cdf = args.file[0]
        is_dev_opt_enbl = int(args.dev[0])

        if not is_dev_opt_enbl:
            logging.info('Running test plan: ' + str(args.plan[0].value))
        # TODO We need to handle plan type and execute test cases accordingly
            if not is_cluster_running():
                logging.error('Cluster is not running. Cluster must be '
                              'running for executing tests')
                exit(-1)
            cluster_status = check_cluster_status(path_to_cdf)
            if cluster_status:
                logging.error('Cluster status reports failure')
                rc = -1
        else:
            logging.info('Running test plan: ' + str(args.plan[0].value))
            test_hare_bootstrap_shutdown(args)

            cluster_status = check_cluster_status(path_to_cdf)
            if cluster_status:
                logging.error('Cluster status reports failure')
                rc = -1

        logging.info('Tests executed successfully')
        exit(rc)
    except Exception as error:
        logging.error('Error while running Hare tests (%s)', error)
        exit(-1)


def reset(args):
    try:
        rc = 0
        util: ConsulUtil = ConsulUtil()

        if is_cluster_running():
            logging.info('Cluster is running, shutting down')
            shutdown_cluster()

        keys: List[KeyDelete] = [
            KeyDelete(name='epoch', recurse=False),
            KeyDelete(name='eq-epoch', recurse=False),
            KeyDelete(name='last_fidk', recurse=False),
            KeyDelete(name='leader', recurse=False),
            KeyDelete(name='m0conf/', recurse=True),
            KeyDelete(name='processes/', recurse=True),
            KeyDelete(name='stats/', recurse=True)
        ]

        logging.info('Deleting Hare KV entries (%s)', keys)
        if not util.kv.kv_delete_in_transaction(keys):
            logging.error('Error during key delete in transaction')
            rc = -1

        exit(rc)
    except Exception as error:
        logging.error('Error during reset (%s)', error)
        exit(-1)


def cleanup(args):
    try:
        rc = -1

        if config_cleanup() == 0 and logs_cleanup() == 0:
            rc = 0

        exit(rc)
    except Exception as error:
        logging.error('Error during cleanup (%s)', error)
        exit(-1)


def logs_cleanup():
    try:
        logging.info('Cleaning up hare log directory(/var/log/seagate/hare)')
        os.system('rm -rf /var/log/seagate/hare')

        return 0
    except Exception as error:
        logging.error('Error during logs cleanup (%s)', error)
        return -1


def config_cleanup():
    try:
        logging.info('Cleaning up hare config directory(/var/lib/hare)')
        os.system('rm -rf /var/lib/hare/*')

        return 0
    except Exception as error:
        logging.error('Error during config cleanup (%s)', error)
        return -1


def generate_support_bundle(args):
    try:
        # Default target directory is /tmp/hare
        cmd = ['hctl', 'reportbug']
        if args.bundleid:
            cmd.append(args.bundleid)
        if args.destdir:
            cmd.append(args.destdir)
        execute(cmd)
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
                                encoding='utf8')
    rpm_search = subprocess.Popen(["grep", "-q", rpm_name],
                                  stdin=rpm_list.stdout,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  encoding='utf8')
    out, err = rpm_search.communicate()
    logging.debug("Output: {}".format(out))
    logging.debug("stderr: {}".format(err))

    return rpm_search.returncode


def is_cluster_running() -> bool:
    return os.system('hctl status >/dev/null') == 0


def nr_services() -> int:
    cmd = ['hctl', 'status', '--json']
    cluster_info = json.loads(execute(cmd))
    # Don't include hax, count it just once later.
    services = {'confd', 'ioservice', 's3server'}
    svcs_nr = 0
    for node in cluster_info['nodes']:
        for svc in node['svcs']:
            if svc['name'] in services:
                svcs_nr += 1
    return svcs_nr + 1


@repeat_if_fails()
def all_services_started(url: str, nr_svcs: int) -> bool:
    conf = ConfStoreProvider(url)
    hostname = conf.get_hostname()
    kv = KVAdapter()
    status_data = kv.kv_get(f'{hostname}/processes', recurse=True)
    statuses = []
    for val in status_data:
        state = val['Value']
        statuses.append(json.loads(state.decode('utf8'))['state'])
    started = [status == 'M0_CONF_HA_PROCESS_STARTED' for status in statuses]
    if len(started) != nr_svcs:
        return False
    return all(started)


def bootstrap_cluster(path_to_cdf: str, domkfs=False):
    if domkfs:
        rc = os.system('hctl bootstrap --mkfs ' + path_to_cdf)
    else:
        rc = os.system('hctl bootstrap ' + path_to_cdf)
    return rc


def wait_for_cluster_start(url: str):
    nr_svcs = nr_services()
    while not all_services_started(url, nr_svcs):
        logging.info('Waiting for all the processes to start..')
        sleep(2)


def shutdown_cluster():
    while is_cluster_running():
        os.system('hctl shutdown --skip-consul-stop')


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


def generate_config(url: str, path_to_cdf: str) -> None:
    conf_dir = '/var/lib/hare'
    os.environ['PATH'] += os.pathsep + '/opt/seagate/cortx/hare/bin/'
    cmd = ['cfgen', '-o', conf_dir, path_to_cdf]
    execute(cmd)
    conf = ConfStoreProvider(url)
    hostname = conf.get_hostname()
    save(f'{conf_dir}/node-name', hostname)


def update_hax_unit(filename: str) -> None:
    try:
        with open(filename) as f:
            contents = f.readlines()
        new_contents = HaxUnitTransformer().transform(contents)
        save(filename, '\n'.join(new_contents))
    except Exception as e:
        raise RuntimeError('Failed to update hax systemd unit: ' + str(e))


def config(args):
    try:
        url = args.config[0]
        filename = args.file[0] or '/var/lib/hare/cluster.yaml'
        save(filename, generate_cdf(url))
        update_hax_unit('/usr/lib/systemd/system/hare-hax.service')
        generate_config(url, filename)
    except Exception as error:
        logging.error('Error performing configuration (%s)', error)
        exit(-1)


def add_subcommand(subparser,
                   command: str,
                   help_str: str,
                   handler_fn: Callable[[Any], None],
                   config_required: bool = True):
    parser = subparser.add_parser(command, help=help_str)
    parser.set_defaults(func=handler_fn)

    parser.add_argument('--config',
                        help='Conf Store URL with cluster info',
                        required=config_required,
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


def add_plan_argument(parser):
    parser.add_argument('--plan',
                        help='Testing plan to be executed. Supported '
                        'values:' + str([e.value for e in Plan]),
                        required=True,
                        nargs=1,
                        type=Plan,
                        action='store')
    return parser


def add_param_argument(parser):
    parser.add_argument('--param',
                        help='Test input URL.',
                        nargs=1,
                        type=str,
                        action='store')
    return parser


def add_dev_argument(parser):
    parser.add_argument('--dev',
                        help='Test Development purpose. Supported '
                        'values: any non zero value',
                        default='0',
                        type=str,
                        action='store')
    return parser


def main():
    p = argparse.ArgumentParser(description='Configure hare settings')
    subparser = p.add_subparsers()

    parser = add_subcommand(subparser,
                            'post_install',
                            help_str='Validates installation',
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
                       help_str='Configures Hare',
                       handler_fn=config))

    add_file_argument(
        add_subcommand(subparser,
                       'init',
                       help_str='Initializes Hare',
                       handler_fn=init))

    add_dev_argument(
        add_param_argument(
            add_plan_argument(
                add_file_argument(
                    add_subcommand(subparser,
                                   'test',
                                   help_str='Tests Hare component',
                                   handler_fn=test_IVT)))))

    sb_sub_parser = add_subcommand(subparser,
                                   'support_bundle',
                                   help_str='Generates support bundle',
                                   handler_fn=generate_support_bundle,
                                   config_required=False)

    sb_sub_parser.add_argument(
        'bundleid',
        metavar='bundle-id',
        type=str,
        nargs='?',
        help='Support bundle ID; defaults to the local host name.')

    sb_sub_parser.add_argument('destdir',
                               metavar='dest-dir',
                               type=str,
                               nargs='?',
                               help='Target directory; defaults to /tmp/hare.')

    add_subcommand(subparser,
                   'reset',
                   help_str='Resets temporary Hare data and configuration',
                   handler_fn=reset,
                   config_required=False)

    add_subcommand(
        subparser,
        'cleanup',
        help_str='Resets Hare configuration, logs and formats Motr metadata',
        handler_fn=cleanup,
        config_required=False)

    add_subcommand(subparser,
                   'prepare',
                   help_str='Validates configuration pre-requisites',
                   handler_fn=noop)

    add_subcommand(subparser,
                   'pre-upgrade',
                   help_str='Performs the Hare rpm pre-upgrade tasks',
                   handler_fn=noop)

    add_subcommand(subparser,
                   'post-upgrade',
                   help_str='Performs the Hare rpm post-upgrade tasks',
                   handler_fn=noop)

    create_logger_directory()
    setup_logging()

    parsed = p.parse_args(sys.argv[1:])

    if not hasattr(parsed, 'func'):
        logging.error('Error: No valid command passed. Please check "--help"')
        exit(1)

    try:
        parsed.func(parsed)
    except Exception as e:
        # TODO refactor all other code to raise exception rather than exitin.
        logging.error(str(e))
        logging.debug('Exiting with FAILED result', exc_info=True)
        exit(1)


if __name__ == '__main__':
    main()
