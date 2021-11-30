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
from dataclasses import dataclass
import inject
import json
import logging
import os
import shutil
import subprocess
import sys
from enum import Enum
from sys import exit
from time import sleep, perf_counter
from typing import Any, Callable, Dict, List
from threading import Event
from urllib.parse import urlparse

import yaml
from cortx.utils.product_features import unsupported_features
from hax.common import di_configuration
from hax.types import KeyDelete
from hax.util import ConsulUtil, repeat_if_fails, KVAdapter
from helper.generate_sysconf import Generator

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider
from hare_mp.systemd import HaxUnitTransformer
from hare_mp.validator import Validator
from hare_mp.utils import execute, Utils
from hare_mp.consul_starter import ConsulStarter
from hare_mp.hax_starter import HaxStarter

import concurrent.futures

# Logger details
LOG_DIR_EXT = '/hare/log/'
LOG_FILE = 'setup.log'
LOG_FILE_SIZE = 5 * 1024 * 1024
CONF_DIR_EXT = '/hare/config/'


class Plan(Enum):
    Sanity = 'sanity'
    Regression = 'regression'
    Full = 'full'
    Performance = 'performance'
    Scalability = 'scalability'


class Svc(Enum):
    All = 'all'
    Hax = 'hax'


def create_logger_directory(log_dir):
    """Create log directory if not exists."""
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception:
            logging.exception(f"{log_dir} Could not be created")
            shutdown_cluster()
            exit(-1)


def setup_logging(url) -> None:
    provider = ConfStoreProvider(url)
    machine_id = provider.get_machine_id()
    log_path = provider.get('cortx>common>storage>log')
    log_dir = log_path + LOG_DIR_EXT + machine_id + '/hare_deployment/'
    log_file = log_dir + LOG_FILE

    create_logger_directory(log_dir)

    console = logging.StreamHandler(stream=sys.stderr)
    fhandler = logging.handlers.RotatingFileHandler(log_file,
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
        # Values supported by below key are - VM, HW, K8
        server_type = provider.get('cortx>common>setup_type')

        # For 'server_type' of 'HW' we will consider env as 'physical' and
        # for 'server_type' of 'VM' and 'K8' we will consider env as virtual
        return 'physical' if server_type == 'HW' else 'virtual'
    except Exception as error:
        logging.error('Cannot get server type (%s)', error)
        return 'unknown'


def logrotate_generic(url: str):
    try:
        with open('/opt/seagate/cortx/hare/conf/logrotate/hare',
                  'r') as f:
            content = f.read()

        log_dir = get_log_dir(url)
        content = content.replace('TMP_LOG_PATH',
                                  log_dir)

        with open('/etc/logrotate.d/hare', 'w') as f:
            f.write(content)

    except Exception as error:
        logging.error('Cannot configure logrotate for hare (%s)', error)


def logrotate(url: str):
    ''' This function is kept incase needed in future.
        This function configures logrotate based on
        'setup_type' key from confstore
    '''
    try:
        server_type = get_server_type(url)
        logging.info('Server type (%s)', server_type)

        if server_type != 'unknown':
            with open(f'/opt/seagate/cortx/hare/conf/logrotate/{server_type}',
                      'r') as f:
                content = f.read()

            log_dir = get_log_dir(url)
            content = content.replace('TMP_LOG_PATH',
                                      log_dir)

            with open('/etc/logrotate.d/hare', 'w') as f:
                f.write(content)

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


def _create_consul_namespace(hare_local_dir: str):
    log_dir = f'{hare_local_dir}/consul/log'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    data_dir = f'{hare_local_dir}/consul/data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    config_dir = f'{hare_local_dir}/consul/config'
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)


def _start_consul(utils: Utils,
                  stop_event: Event,
                  hare_local_dir: str,
                  hare_log_dir: str,
                  url: str):
    log_dir = hare_log_dir
    data_dir = f'{hare_local_dir}/consul/data'
    config_dir = f'{hare_local_dir}/consul/config'

    provider = ConfStoreProvider(url)
    consul_endpoints = provider.get('cortx>external>consul>endpoints')

    # remove tcp://
    peers = []
    for endpoint in consul_endpoints:
        key = endpoint.split('/')
        peer = ('/'.join(key[2:]))
        peers.append(peer)

    consul_starter = ConsulStarter(utils=utils, stop_event=stop_event,
                                   log_dir=log_dir, data_dir=data_dir,
                                   config_dir=config_dir, peers=peers)
    consul_starter.start()

    return consul_starter


def _start_hax(utils: Utils,
               stop_event: Event,
               hare_local_dir: str,
               hare_log_dir: str) -> HaxStarter:
    if not os.path.exists(hare_local_dir):
        os.makedirs(hare_local_dir)
    if not os.path.exists(hare_log_dir):
        os.makedirs(hare_log_dir)
    hax_starter = HaxStarter(utils=utils, stop_event=stop_event,
                             home_dir=hare_local_dir, log_dir=hare_log_dir)
    hax_starter.start()
    return hax_starter


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
            logrotate_generic(args.config[0])

    except Exception as error:
        logging.error('Error while checking installed rpms (%s)', error)
        exit(-1)


def enable_hare_consul_agent() -> None:
    cmd = ['systemctl', 'enable', 'hare-consul-agent']
    execute(cmd)


def disable_hare_consul_agent() -> None:
    cmd = ['systemctl', 'disable', 'hare-consul-agent']
    execute(cmd)


def prepare(args):
    url = args.config[0]
    utils = Utils(ConfStoreProvider(url))
    stop_event = Event()
    conf_dir = get_config_dir(url)
    log_dir = get_log_dir(url)
    _create_consul_namespace(conf_dir)
    consul_starter = _start_consul(utils, stop_event, conf_dir, log_dir, url)
    utils.save_node_facts()
    utils.save_drives_info()
    try:
        util: ConsulUtil = ConsulUtil()
        sess = util.get_leader_session_no_wait()
        util.destroy_session(sess)
    except Exception:
        logging.debug('No leader is elected yet')

    consul_starter.stop()


def init_with_bootstrap(args):
    try:
        rc = 0
        url = args.config[0]
        validator = Validator(ConfStoreProvider(url))
        disable_hare_consul_agent()
        if validator.is_first_node_in_cluster():
            if args.file:
                path_to_cdf = args.file[0]
            else:
                path_to_cdf = get_config_dir(url) + '/cluster.yaml'
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
        shutdown_cluster()
        raise RuntimeError(f'Error while initializing cluster :key={error}')


def start_hax_with_systemd():
    cmd = ['systemctl', 'start', 'hare-hax']
    execute(cmd)


def start_crond():
    cmd = ['/usr/sbin/crond', 'start']
    execute(cmd)


def start_hax_and_consul_without_systemd(url: str, utils: Utils):
    conf_dir = get_config_dir(url)
    log_dir = get_log_dir(url)
    # Event on which hare receives a notification in case consul agent or hax
    # terminates.
    hare_stop_event = Event()
    consul_starter = _start_consul(utils, hare_stop_event,
                                   conf_dir, log_dir, url)
    hax_starter = _start_hax(utils, hare_stop_event, conf_dir, log_dir)
    hare_stop_event.wait()
    if utils.is_hare_stopping():
        consul_starter.stop()
        hax_starter.stop()


def start(args):
    url = args.config[0]
    utils = Utils(ConfStoreProvider(url))
    logrotate_generic(url)
    start_crond()
    if args.systemd:
        start_hax_with_systemd()
    else:
        # This is a blocking call and will block until either consul
        # or hax process terminates.
        # TODO: Check if the respective processes need to be restarted.
        start_hax_and_consul_without_systemd(url, utils)


@dataclass
class ProcessStartInfo:
    cmd: List[str]
    hostname: str
    fid: str


def start_mkfs(proc_to_start: ProcessStartInfo) -> int:
    try:
        logging.info('Starting mkfs process [fid=%s] at hostname=%s',
                     proc_to_start.fid, proc_to_start.hostname)
        command = proc_to_start.cmd
        execute(command)
        logging.info('Started mkfs process [fid=%s]', proc_to_start.fid)
        rc = 0
    except Exception as error:
        logging.error('Error launching mkfs [fid=%s] at hostname=%s: %s',
                      proc_to_start.fid, proc_to_start.hostname, error)
        rc = -1
    return rc


def start_mkfs_parallel(hostname: str, hare_config_dir: str):
    # TODO: path needs to be updated according to the new conf-store key
    sysconfig_dir = '/etc/sysconfig/'
    src = f'{hare_config_dir}/sysconfig/motr/{hostname}'
    for file in os.listdir(src):
        shutil.copy(os.path.join(src, file), sysconfig_dir)

    generator = Generator(hostname,
                          hare_config_dir,
                          kv_file=f'{hare_config_dir}/consul-kv.json')
    cmd = '/usr/libexec/cortx-motr/motr-mkfs'
    # start mkfs for confd, ios services
    start = perf_counter()
    cmd_list: List[ProcessStartInfo] = []
    for svc in ('confd', 'ios'):
        svc_fids = generator.get_svc_fids(svc)
        for fid in svc_fids:
            # real command line
            cmd_line = [cmd, fid, '--conf']
            process = ProcessStartInfo(cmd=cmd_line,
                                       hostname=hostname,
                                       fid=fid)
            cmd_list.append(process)

    ret_values = []
    with concurrent.futures.ProcessPoolExecutor() as executor:
        ret_values = list(executor.map(start_mkfs, cmd_list))
    finish = perf_counter()
    perf_result = finish - start

    if not all(rc == 0 for rc in ret_values):
        raise RuntimeError('One or more mkfs processes failed to start. '
                           'Please check the logs above for details.')
    else:
        logging.info(f'Total time taken for all mkfs on this node = '
                     f'{perf_result}\n\n')


def init(args):
    try:
        url = args.config[0]
        utils = Utils(ConfStoreProvider(url))
        stop_event = Event()
        config_dir = get_config_dir(url)
        log_dir = get_log_dir(url)
        # Starting consul and hax
        consul_starter = _start_consul(utils, stop_event,
                                       config_dir, log_dir, url)
        hax_starter = _start_hax(utils, stop_event, config_dir, log_dir)
        hostname = utils.get_local_hostname()
        start_mkfs_parallel(hostname, config_dir)
        # Stopping hax and consul
        hax_starter.stop()
        consul_starter.stop()
    except Exception as error:
        if hax_starter:
            hax_starter.stop()
        if consul_starter:
            consul_starter.stop()
        raise RuntimeError(f'Error while initializing cluster :key={error}')


def test(args):
    try:
        rc = 0
        url = args.config[0]
        validator = Validator(ConfStoreProvider(url))
        if validator.is_first_node_in_cluster():
            if args.file:
                path_to_cdf = args.file[0]
            else:
                path_to_cdf = get_config_dir(url) + '/cluster.yaml'
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


def test_IVT(args):
    try:
        rc = 0
        if args.file:
            path_to_cdf = args.file[0]
        else:
            path_to_cdf = get_config_dir(args.config[0]) + '/cluster.yaml'

        logging.info('Running test plan: ' + str(args.plan[0].value))
        # TODO We need to handle plan type and execute test cases accordingly
        if not is_cluster_running():
            logging.error('Cluster is not running. Cluster must be running '
                          'for executing tests')
            exit(-1)
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
        # In motr reset, motr clean up the motr and IO tests generated data.
        # But to restart the cluster, hare init needed to be called.
        # As a part of motr reset, we need to mkfs and start m0d services,
        # motr wants hare to start it through hare init.
        # So its not actually cluster start but it is services start.
        init(args)
        exit(0)
    except Exception as error:
        logging.error('Error during reset (%s)', error)
        exit(-1)


def kv_cleanup():
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
        raise RuntimeError('Error during key delete in transaction')


def pre_factory(url):
    logging.info('Executing pre-factory cleanup command...')
    deployment_logs_cleanup(url)
    motr_cleanup()


def get_log_dir(url) -> str:
    provider = ConfStoreProvider(url)
    machine_id = provider.get_machine_id()
    log_path = provider.get('cortx>common>storage>log')
    return log_path + LOG_DIR_EXT + machine_id


def get_config_dir(url) -> str:
    provider = ConfStoreProvider(url)
    machine_id = provider.get_machine_id()
    config_path = provider.get('cortx>common>storage>local')
    return config_path + CONF_DIR_EXT + '/' + machine_id


def cleanup(args):
    try:
        kv_cleanup()
        url = args.config[0]
        logs_cleanup(url)
        config_cleanup(url)
        if args.pre_factory:
            pre_factory(url)

        exit(0)
    except Exception as error:
        logging.error('Error during cleanup (%s)', error)
        exit(-1)


def logs_cleanup(url):
    try:
        log_dir = get_log_dir(url)

        logging.info(f'Cleaning up hare log directory({log_dir})')
        os.system(f'rm -f {log_dir}/*')

    except Exception as error:
        raise RuntimeError(f'Error during logs cleanup : key={error}')


def config_cleanup(url):
    try:
        config_dir = get_config_dir(url)

        logging.info(f'Cleaning up hare config directory({config_dir})')
        os.system(f'rm -rf {config_dir}/*')

    except Exception as error:
        raise RuntimeError(f'Error during config cleanup : key={error}')


def deployment_logs_cleanup(url):
    try:
        log_dir = get_log_dir(url)
        deployment_logs_dir = log_dir + 'hare_deployment'

        logging.info(f'Cleaning up hare deployment log directory'
                     f' ({deployment_logs_dir})')
        os.system(f'rm -rf {deployment_logs_dir}')

    except Exception as error:
        raise RuntimeError(f'Error during deployment log cleanup: key={error}')


def motr_cleanup():
    try:
        logging.info('Cleaning up motr directory(/var/motr/hax)')
        os.system('rm -rf /var/motr/hax')
        logging.info('Cleaning up sysconfig files(/etc/sysconfig/m0d-*)')
        os.system('rm -rf /etc/sysconfig/m0d-0x7200000000000001*')
        logging.info('Cleaning up sysconfig files(/etc/sysconfig/s3server-*)')
        os.system('rm -rf /etc/sysconfig/s3server-0x7200000000000001*')

    except Exception as error:
        raise RuntimeError(f'Error during motr cleanup: key={error}')


def generate_support_bundle(args):
    try:
        # Default target directory is /tmp/hare
        cmd = ['hctl', 'reportbug']
        if args.b:
            cmd.append('-b')
            cmd.append(args.b[0])
        if args.t:
            cmd.append('-t')
            cmd.append(args.t[0])
        if args.duration:
            logging.info("Time bound log collection for %s", args.duration)
        if args.size_limit:
            logging.info("Collected limited sized logs: %s", args.size_limit)
        if args.services:
            logging.info("Logs collection limiting to a single or multiple"
                         " service specific logs: %s", args.services)
        if args.binlogs:
            logging.info("Include the binary logs? %s", args.binlogs)
        if args.coredumps:
            logging.info("Include core dumps? %s ", args.coredumps)
        if args.stacktrace:
            logging.info("Include stacktraces? %s", args.stacktrace)

        url = args.config[0]
        log_dir = get_log_dir(url)
        conf_dir = get_config_dir(url)
        cmd.append('-l')
        cmd.append(log_dir)
        cmd.append('-c')
        cmd.append(conf_dir)

        provider = ConfStoreProvider(url)
        if provider.get('cortx>common>setup_type') == 'K8':
            cmd.append('--no-systemd')

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
    utils = Utils(ConfStoreProvider(url))
    hostname = utils.get_local_hostname()
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


def generate_cdf(url: str, motr_md_url: str) -> str:
    # ConfStoreProvider creates an empty file, if file does not exist.
    # So, we are validating the file is present or not.
    if not os.path.isfile(urlparse(motr_md_url).path):
        raise FileNotFoundError(f'config file: {motr_md_url} does not exist')
    motr_provider = ConfStoreProvider(motr_md_url, index='motr_md')
    generator = CdfGenerator(ConfStoreProvider(url), motr_provider)
    return generator.generate()


def save(filename: str, contents: str) -> None:
    directory = os.path.dirname(filename)
    os.makedirs(directory, exist_ok=True)
    with open(filename, 'w') as f:
        f.write(contents)


def generate_config(url: str, path_to_cdf: str) -> None:
    provider = ConfStoreProvider(url)
    utils = Utils(provider)
    conf_dir = get_config_dir(url)
    path = os.getenv('PATH')
    if path:
        path += os.pathsep + '/opt/seagate/cortx/hare/bin/'
    python_path = os.pathsep.join(sys.path)
    cmd = ['configure', '-c', conf_dir, path_to_cdf,
           '--log-dir', get_log_dir(url),
           '--log-file', LOG_FILE,
           '--uuid', provider.get_machine_id()]
    execute(cmd, env={'PYTHONPATH': python_path, 'PATH': path,
                      'LC_ALL': "en_US.utf-8", 'LANG': "en_US.utf-8"})
    utils.copy_conf_files(conf_dir)
    utils.copy_consul_files(conf_dir, mode='client')
    utils.import_kv(conf_dir)


def update_hax_unit(filename: str) -> None:
    try:
        with open(filename) as f:
            contents = f.readlines()
        new_contents = HaxUnitTransformer().transform(contents)
        save(filename, '\n'.join(new_contents))
    except Exception as e:
        raise RuntimeError('Failed to update hax systemd unit: ' + str(e))


def config(args):
    consul_starter = None
    try:
        url = args.config[0]
        utils = Utils(ConfStoreProvider(url))
        stop_event = Event()
        conf_dir = get_config_dir(url)
        log_dir = get_log_dir(url)
        consul_starter = _start_consul(utils, stop_event,
                                       conf_dir, log_dir, url)
        if args.file:
            filename = args.file[0]
        else:
            filename = get_config_dir(url) + '/cluster.yaml'

        provider = ConfStoreProvider(url)
        config_path = provider.get('cortx>common>storage>local')
        machine_id = provider.get_machine_id()
        motr_md_path = config_path + '/motr/' + machine_id
        motr_md_url = 'json://' + motr_md_path + '/motr_hare_keys.json'

        save(filename, generate_cdf(url, motr_md_url))
        update_hax_unit('/usr/lib/systemd/system/hare-hax.service')
        generate_config(url, filename)
        consul_starter.stop()
    except Exception as error:
        logging.error('Error performing configuration (%s)', error)
        if consul_starter:
            consul_starter.stop()
        exit(-1)


def add_subcommand(subparser,
                   command: str,
                   help_str: str,
                   handler_fn: Callable[[Any], None],
                   config_required: bool = True):
    parser = subparser.add_parser(command, help=help_str)
    parser.set_defaults(func=handler_fn)

    parser.add_argument('--config', '-c',
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


def add_factory_argument(parser):
    parser.add_argument('--pre-factory',
                        help="""Deletes contents of hare log directory,
                        hare config dir and /var/motr. Undoes everything that
                        is done in post-install stage of hare provisioner""",
                        required=False,
                        action='store_true')
    return parser


def add_service_argument(parser):
    parser.add_argument('--services', '-s',
                        help='Services to be setup. Supported '
                        'values: ' + str([s.value for s in Svc]),
                        nargs=1,
                        type=Svc,
                        action='store')
    return parser


def add_systemd_argument(parser):
    parser.add_argument('--systemd',
                        help="""Start Hare servies using systemd interface,
                        by default start command assumes systemd interface
                        is not enebaled""",
                        required=False,
                        action='store_true')
    return parser


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def main():
    inject.configure(di_configuration)
    p = argparse.ArgumentParser(description='Configure hare settings')
    subparser = p.add_subparsers()

    parser = add_service_argument(
        add_subcommand(subparser,
                       'post_install',
                       help_str='Validates installation',
                       handler_fn=post_install))
    parser.add_argument(
        '--report-unavailable-features',
        help='Report unsupported features according to setup type',
        action='store_true')
    parser.add_argument('--configure-logrotate',
                        help='Configure logrotate for hare',
                        action='store_true')

    add_service_argument(
        add_file_argument(
            add_subcommand(subparser,
                           'config',
                           help_str='Configures Hare',
                           handler_fn=config)))

    add_service_argument(
        add_file_argument(
            add_subcommand(subparser,
                           'init',
                           help_str='Initializes Hare',
                           handler_fn=init)))

    add_systemd_argument(
        add_service_argument(
            add_file_argument(
                add_subcommand(subparser,
                               'start',
                               help_str='Starts Hare services',
                               handler_fn=start))))

    add_service_argument(
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
                                   handler_fn=generate_support_bundle)

    sb_sub_parser.add_argument(
        '-b',
        type=str,
        nargs=1,
        help='Unique bundle-id used to identify support bundles; '
             'defaults to the local host name.',
        action='store')

    sb_sub_parser.add_argument(
        '-t',
        type=str,
        nargs=1,
        help='Target directory; defaults to /tmp/hare.',
        action='store')

    sb_sub_parser.add_argument(
        '--duration',
        type=str,
        nargs=1,
        help='ISO 8061 format, "P" separates, the start datetime and duration'
             'to be considered after that. "T" separated date and time. '
             'Default is P5d.',
        action='store')

    sb_sub_parser.add_argument(
        '--size_limit',
        type=str,
        nargs=1,
        help='Limit set on per component for its support bundle size.'
             'eg. "1G" for 1GB or "100M" for 100 MB. Default -> 0, '
             'for no size limit.',
        action='store')

    sb_sub_parser.add_argument(
        '--services',
        type=str,
        nargs=1,
        help='"|" pipe separated service names for the services for '
             'which logs needs to be collected. Default is "All".',
        action='store')

    sb_sub_parser.add_argument(
        '--binlogs',
        type=str2bool,
        nargs='?',
        const=True,
        default=True,
        help='Logs collection for given type of logs (text, binary,'
             ' etc), as applicable per component',
        action='store')

    sb_sub_parser.add_argument(
        '--coredumps',
        type=str2bool,
        nargs='?',
        const=False,
        default=False,
        help='Include or exclude core dumps, exclude by default',
        action='store')

    sb_sub_parser.add_argument(
        '--stacktrace',
        type=str2bool,
        nargs='?',
        const=False,
        default=False,
        help='Include or exclude stack traces, include by default',
        action='store')

    add_service_argument(
        add_file_argument(
            add_subcommand(subparser,
                           'reset',
                           help_str='Resets temporary Hare data'
                                    ' and configuration',
                           handler_fn=reset)))

    add_service_argument(
        add_factory_argument(
            add_subcommand(
                subparser,
                'cleanup',
                help_str='Resets Hare configuration,'
                         ' logs & formats Motr metadata',
                handler_fn=cleanup)))

    add_service_argument(
        add_subcommand(subparser,
                       'prepare',
                       help_str='Validates configuration pre-requisites',
                       handler_fn=prepare))

    add_service_argument(
        add_subcommand(subparser,
                       'pre-upgrade',
                       help_str='Performs the Hare rpm pre-upgrade tasks',
                       handler_fn=noop))

    add_service_argument(
        add_subcommand(subparser,
                       'post-upgrade',
                       help_str='Performs the Hare rpm post-upgrade tasks',
                       handler_fn=noop))

    add_service_argument(
        add_subcommand(subparser,
                       'upgrade',
                       help_str='Performs the Hare rpm upgrade tasks',
                       handler_fn=noop,
                       config_required=False))

    parsed = p.parse_args(sys.argv[1:])

    setup_logging(parsed.config[0])

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
