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

# Setup utility for Hare to configure Hare related settings, e.g. logrotate
# etc.

import argparse
from dataclasses import dataclass
import inject
import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import socket
import psutil
import uuid
from enum import Enum
from sys import exit
from time import sleep, perf_counter
from typing import Any, Callable, Dict, List
from threading import Event

import yaml
from cortx.utils.cortx import Const
from hax.common import di_configuration
from hax.types import KeyDelete, Fid
from hax.util import ConsulUtil, repeat_if_fails, KVAdapter
from helper.generate_sysconf import Generator

from hare_mp.cdf import CdfGenerator
from hare_mp.store import ConfStoreProvider
from hare_mp.systemd import HaxUnitTransformer
from hare_mp.validator import Validator
from hare_mp.utils import execute, func_log, func_enter, func_leave, Utils
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


# Note: func_log method will not work for this function as the
# relevant log dir does not exists.
def create_logger_directory(log_dir):
    """Create log directory if not exists."""
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception as e:
            logging.exception(f"{log_dir} Could not be created")
            shutdown_cluster()
            raise RuntimeError("Failed to create log directory " + str(e))


def setup_logging(url) -> None:
    provider = ConfStoreProvider(url)
    machine_id = provider.get_machine_id()
    log_path = provider.get('cortx>common>storage>log')
    log_dir = log_path + LOG_DIR_EXT + machine_id + '/hare_deployment/'
    log_file = log_dir + LOG_FILE

    create_logger_directory(log_dir)

    console = logging.StreamHandler(stream=sys.stdout)
    fhandler = logging.handlers.RotatingFileHandler(log_file,
                                                    maxBytes=LOG_FILE_SIZE,
                                                    mode='a',
                                                    backupCount=5,
                                                    encoding=None,
                                                    delay=False)
    logging.basicConfig(level=logging.INFO,
                        handlers=[console, fhandler],
                        format='%(asctime)s [%(levelname)s] %(message)s')


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
def is_mkfs_required(url: str) -> bool:
    try:
        conf = ConfStoreProvider(url)
        utils = Utils(conf)
        machine_id = conf.get_machine_id()
        return utils.is_motr_io_present(machine_id)
    except Exception as error:
        logging.warn('Failed to get pod type (%s). Current stage will '
                     'be assumed as not required by default', error)

        return False


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
def has_process_started(proc_name: str) -> bool:
    for process in psutil.process_iter():
        if proc_name.lower() in process.name().lower():
            return True
    return False


@func_log(func_enter, func_leave)
def has_process_stopped(proc_name: str) -> bool:
    for process in psutil.process_iter():
        if proc_name.lower() in process.name().lower():
            return False
    return True


@repeat_if_fails()
def save_consul_node_name(cns_utils: ConsulUtil, consul_nodename: str,
                          hostname: str):
    cns_utils.kv.kv_put(f'consul/node/{hostname}', consul_nodename)


@func_log(func_enter, func_leave)
def _start_consul(utils: Utils,
                  stop_event: Event,
                  hare_local_dir: str,
                  hare_log_dir: str,
                  url: str):
    log_dir = hare_log_dir
    data_dir = f'{hare_local_dir}/consul/data'
    config_dir = f'{hare_local_dir}/consul/config'

    provider = ConfStoreProvider(url)
    node_id = uuid.uuid4()
    consul_endpoints = provider.get('cortx>external>consul>endpoints')
    cns_utils: ConsulUtil = ConsulUtil()
    hostname = utils.get_local_hostname()

    # remove tcp://
    peers = []
    for endpoint in consul_endpoints:
        key = endpoint.split('/')
        # Considering tcp endpoints only. Ignoring all other endpoints.
        if key[0] != 'tcp:':
            continue
        peer = ('/'.join(key[2:]))
        peers.append(peer)

    bind_addr = socket.gethostbyname(hostname)
    consul_nodename = hostname + ':' + str(node_id)[:8]
    consul_starter = ConsulStarter(utils=utils, cns_utils=cns_utils,
                                   stop_event=stop_event,
                                   log_dir=log_dir, data_dir=data_dir,
                                   config_dir=config_dir,
                                   node_id=str(node_id),
                                   node_name=consul_nodename,
                                   peers=peers, bind_addr=bind_addr)
    consul_starter.start()
    save_consul_node_name(cns_utils, consul_nodename, hostname)

    return consul_starter


@func_log(func_enter, func_leave)
def _stop_consul(consul_starter: ConsulStarter) -> bool:
    try:
        consul_starter.stop()
        consul_starter.join()
    except Exception:
        return False
    return True


@func_log(func_enter, func_leave)
def stop_consul_blocking(consul_starter: ConsulStarter):
    while not _stop_consul(consul_starter):
        logging.debug('Stopping Consul...')
        sleep(5)


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
def _stop_hax(hax_starter: HaxStarter) -> bool:
    try:
        hax_starter.stop()
        hax_starter.join()
    except Exception:
        return False
    return True


@func_log(func_enter, func_leave)
def stop_hax_blocking(hax_starter: HaxStarter):
    while not _stop_hax(hax_starter):
        logging.debug('Stopping hax...')
        sleep(5)


@func_log(func_enter, func_leave)
def post_install(args):

    checkRpm('cortx-motr')
    checkRpm('consul')
    checkRpm('cortx-hare')
    checkRpm('cortx-py-utils')
    # we need to check for 'rgw' rpm
    # checkRpm('cortx-s3server')

    if args.configure_logrotate:
        logrotate_generic(args.config[0])


def enable_hare_consul_agent() -> None:
    cmd = ['systemctl', 'enable', 'hare-consul-agent']
    execute(cmd)


def disable_hare_consul_agent() -> None:
    cmd = ['systemctl', 'disable', 'hare-consul-agent']
    execute(cmd)


@func_log(func_enter, func_leave)
def prepare(args):
    url = args.config[0]
    utils = Utils(ConfStoreProvider(url))
    stop_event = Event()
    conf_dir = get_config_dir(url)
    log_dir = get_log_dir(url)
    _create_consul_namespace(conf_dir)
    consul_starter = _start_consul(utils, stop_event, conf_dir, log_dir, url)
    utils.save_config_path(url)
    utils.save_log_path()
    utils.save_node_facts()
    utils.save_drives_info()
    try:
        util: ConsulUtil = ConsulUtil()
        sess = util.get_leader_session_no_wait()
        util.destroy_session(sess)
    except Exception:
        logging.debug('No leader is elected yet')

    stop_consul_blocking(consul_starter)


def get_hare_motr_s3_processes(utils: ConsulUtil) -> Dict[str, List[Fid]]:
    nodes = utils.catalog.get_node_names()
    processes: Dict[str, List[Fid]] = {}
    for node in nodes:
        processes[node] = utils.get_node_hare_motr_s3_fids(node)
    return processes


def init_with_bootstrap(args):
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
            raise RuntimeError('Failed to bootstrap the cluster')

        wait_for_cluster_start(url)
        shutdown_cluster()
    enable_hare_consul_agent()


def start_hax_with_systemd():
    cmd = ['systemctl', 'start', 'hare-hax']
    execute(cmd)


def start_crond():
    cmd = ['/usr/sbin/crond', 'start']
    execute(cmd)


@func_log(func_enter, func_leave)
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
        stop_consul_blocking(consul_starter)
        stop_hax_blocking(hax_starter)


def start(args):
    logging.info('Starting Hare services')
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


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
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
        logging.debug(f'Total time taken for all mkfs on this node = '
                      f'{perf_result}\n\n')


@repeat_if_fails()
def is_mkfs_done_on_all_nodes(utils: Utils,
                              cns_utils: ConsulUtil,
                              nodes: List[str]) -> bool:
    for node in nodes:
        if not cns_utils.kv.kv_get(f'mkfs_done/{node}',
                                   recurse=True,
                                   allow_null=True):
            return False
    return True


@func_log(func_enter, func_leave)
@repeat_if_fails()
def cleanup_mkfs_state(utils: Utils, cns_utils: ConsulUtil):
    hostname = utils.get_local_hostname()
    keys: List[KeyDelete] = [
        KeyDelete(name=f'mkfs_done/{hostname}', recurse=True),
    ]

    if not cns_utils.kv.kv_delete_in_transaction(keys):
        logging.error('Delete transaction failed for %s', keys)


@func_log(func_enter, func_leave)
@repeat_if_fails()
def set_mkfs_done_for(node: str, cns_utils: ConsulUtil):
    cns_utils.kv.kv_put(f'mkfs_done/{node}', 'true')


@func_log(func_enter, func_leave)
def init(args):
    try:
        url = args.config[0]

        if not is_mkfs_required(url):
            return

        conf = ConfStoreProvider(url)
        utils = Utils(conf)
        cns_utils = ConsulUtil()
        stop_event = Event()
        config_dir = get_config_dir(url)
        log_dir = get_log_dir(url)
        # Starting consul and hax
        consul_starter = _start_consul(utils, stop_event,
                                       config_dir, log_dir, url)
        hax_starter = _start_hax(utils, stop_event, config_dir, log_dir)
        hostname = utils.get_local_hostname()
        # Cleanup old mkfs state
        cleanup_mkfs_state(utils, cns_utils)
        start_mkfs_parallel(hostname, config_dir)
        # Update mkfs state
        set_mkfs_done_for(hostname, cns_utils)
        data_nodes = conf.get_hostnames_for_service(
            Const.SERVICE_MOTR_IO.value)

        # Wait for other nodes to complete.
        # This will block.
        while not is_mkfs_done_on_all_nodes(utils, cns_utils,
                                            data_nodes):
            sleep(5)
        # Stopping hax and consul
        stop_hax_blocking(hax_starter)
        stop_consul_blocking(consul_starter)
    except Exception as error:
        if hax_starter:
            stop_hax_blocking(hax_starter)
        if consul_starter:
            stop_consul_blocking(consul_starter)
        raise RuntimeError(f'Error while initializing cluster :key={error}')


@func_log(func_enter, func_leave)
def test(args):
    try:
        url = args.config[0]
        validator = Validator(ConfStoreProvider(url))
        if validator.is_first_node_in_cluster():
            if args.file:
                path_to_cdf = args.file[0]
            else:
                path_to_cdf = get_config_dir(url) + '/cluster.yaml'
            if not is_cluster_running() and bootstrap_cluster(path_to_cdf):
                raise RuntimeError("Failed to bootstrap the cluster")
            cluster_status = check_cluster_status(path_to_cdf)

            wait_for_cluster_start(url)
            if cluster_status:
                raise RuntimeError(f'Cluster status reports failure :'
                                   f' {cluster_status}')

    finally:
        shutdown_cluster()


def test_IVT(args):
    if args.file:
        path_to_cdf = args.file[0]
    else:
        path_to_cdf = get_config_dir(args.config[0]) + '/cluster.yaml'

    logging.info('Running test plan: ' + str(args.plan[0].value))
    # TODO We need to handle plan type and execute test cases accordingly
    if not is_cluster_running():
        raise RuntimeError('Cluster is not running. '
                           'Cluster must be running for executing tests')
    cluster_status = check_cluster_status(path_to_cdf)
    if cluster_status:
        raise RuntimeError(f'Cluster status reports failure : '
                           f' {cluster_status}')

    logging.info('Tests executed successfully')


def reset(args):
    try:
        # In motr reset, motr clean up the motr and IO tests generated data.
        # But to restart the cluster, hare init needed to be called.
        # As a part of motr reset, we need to mkfs and start m0d services,
        # motr wants hare to start it through hare init.
        # So its not actually cluster start but it is services start.
        init(args)
    except Exception as error:
        raise RuntimeError(f'Error during reset : {error}')


@func_log(func_enter, func_leave)
@repeat_if_fails()
def cleanup_node_facts(utils: Utils, cns_utils: ConsulUtil):
    hostname = utils.get_local_hostname()
    keys: List[KeyDelete] = [
        KeyDelete(name=f'{hostname}/facts', recurse=True),
    ]

    if not cns_utils.kv.kv_delete_in_transaction(keys):
        logging.error('Delete transaction failed for %s', keys)


@func_log(func_enter, func_leave)
@repeat_if_fails()
def cleanup_disks_info(utils: Utils, cns_utils: ConsulUtil):
    hostname = utils.get_local_hostname()
    keys: List[KeyDelete] = [
        KeyDelete(name=f'{hostname}/drives', recurse=True),
    ]

    if not cns_utils.kv.kv_delete_in_transaction(keys):
        logging.error('Delete transaction failed for %s', keys)


@func_log(func_enter, func_leave)
def kv_cleanup(url):
    util: ConsulUtil = ConsulUtil()
    conf = ConfStoreProvider(url)
    utils = Utils(conf)
    cleanup_disks_info(utils, util)
    cleanup_node_facts(utils, util)

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
        KeyDelete(name='stats/', recurse=True),
        KeyDelete(name='mkfs/', recurse=True),
        KeyDelete(name='bytecount/', recurse=True),
        KeyDelete(name='config_path', recurse=False),
        KeyDelete(name='failvec', recurse=False),
        KeyDelete(name='m0_client_types', recurse=True)
    ]

    logging.info('Deleting Hare KV entries (%s)', keys)
    if not util.kv.kv_delete_in_transaction(keys):
        raise RuntimeError('Error during key delete in transaction')


def pre_factory(url):
    logging.info('Executing pre-factory cleanup command...')
    deployment_logs_cleanup(url)
    motr_cleanup()


@func_log(func_enter, func_leave)
def get_log_dir(url) -> str:
    provider = ConfStoreProvider(url)
    machine_id = provider.get_machine_id()
    log_path = provider.get('cortx>common>storage>log')
    return log_path + LOG_DIR_EXT + machine_id


@func_log(func_enter, func_leave)
def get_config_dir(url) -> str:
    provider = ConfStoreProvider(url)
    machine_id = provider.get_machine_id()
    config_path = provider.get('cortx>common>storage>local')
    return config_path + CONF_DIR_EXT + '/' + machine_id


@func_log(func_enter, func_leave)
def cleanup(args):
    try:
        url = args.config[0]
        kv_cleanup(url)
        logs_cleanup(url)
        config_cleanup(url)
        if args.pre_factory:
            pre_factory(url)

    except Exception as error:
        raise RuntimeError(f'Error during cleanup : {error}')


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


@func_log(func_enter, func_leave)
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

        execute(cmd)
    except Exception as error:
        raise RuntimeError(f'Error while generating support bundle : {error}')


def noop(args):
    pass


@func_log(func_enter, func_leave)
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
    if out:
        logging.info("Output: %s", out)
    logging.info("RPM: %s found", rpm_name)
    if err:
        logging.info("Stderr: %s", err)
    if rpm_search.returncode != 0:
        raise RuntimeError(f"rpm {rpm_name} is missing")


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
def all_services_started(url: str, processes: Dict[str, List[Fid]]) -> bool:
    kv = KVAdapter()
    if not processes:
        return False
    for key in processes.keys():
        for proc_fid in processes[key]:
            proc_state = kv.kv_get(f'{key}/processes/{proc_fid}',
                                   recurse=True,
                                   allow_null=True)
            if proc_state:
                proc_state_val = proc_state[0]['Value']
                state = json.loads(proc_state_val.decode('utf8'))['state']
                if state not in ('M0_CONF_HA_PROCESS_STARTED',
                                 'M0_CONF_HA_PROCESS_DTM_RECOVERED'):
                    return False
            else:
                return False
    return True


def bootstrap_cluster(path_to_cdf: str, domkfs=False):
    if domkfs:
        rc = os.system('hctl bootstrap --mkfs ' + path_to_cdf)
    else:
        rc = os.system('hctl bootstrap ' + path_to_cdf)
    return rc


def wait_for_cluster_start(url: str):
    util: ConsulUtil = ConsulUtil()
    processes: Dict[str, List[Fid]] = {}
    while not processes:
        processes = get_hare_motr_s3_processes(util)
    while not all_services_started(url, processes):
        logging.info('Waiting for all the processes to start..')
        sleep(2)


@func_log(func_enter, func_leave)
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


@func_log(func_enter, func_leave)
def generate_cdf(url: str) -> str:
    generator = CdfGenerator(ConfStoreProvider(url))
    return generator.generate()


def save(filename: str, contents: str) -> None:
    directory = os.path.dirname(filename)
    os.makedirs(directory, exist_ok=True)
    with open(filename, 'w') as f:
        f.write(contents)


@func_log(func_enter, func_leave)
@repeat_if_fails()
def is_kv_imported(utils: Utils) -> bool:
    try:
        leader = utils.kv.kv_get('leader', allow_null=True)
        if not leader or leader is None:
            return False
    except Exception:
        raise RuntimeError('Failed to get leader key')
    return True


@func_log(func_enter, func_leave)
def generate_config(url: str, path_to_cdf: str) -> None:
    provider = ConfStoreProvider(url)
    utils = Utils(provider)
    conf_dir = get_config_dir(url)
    path = os.getenv('PATH')
    if path:
        path += os.pathsep + '/opt/seagate/cortx/hare/bin/'
    python_path = os.pathsep.join(sys.path)
    transport_type = utils.get_transport_type()
    cmd = ['configure', '-c', conf_dir, path_to_cdf,
           '--transport', transport_type,
           '--log-dir', get_log_dir(url),
           '--log-file', LOG_FILE,
           '--uuid', provider.get_machine_id()]

    locale_info = execute(['locale', '-a'])
    env = {'PYTHONPATH': python_path, 'PATH': path}

    if 'en_US.utf-8' in locale_info or 'en_US.utf8' in locale_info:
        env.update({'LC_ALL': "en_US.utf-8", 'LANG': "en_US.utf-8"})

    execute(cmd, env)

    utils.copy_conf_files(conf_dir)
    utils.copy_consul_files(conf_dir, mode='client')
    # consul-kv.json contains key values for the entire cluster. Thus,
    # it is sufficent to import consul-kv just once. We fetch one of
    # the consul kv to check if the key-values were already imported
    # during start up of one of the nodes in the cluster, this avoids
    # duplicate imports and thus a possible overwriting of the updated
    # cluster state.
    if not is_kv_imported(utils):
        utils.import_kv(conf_dir)


@func_log(func_enter, func_leave)
def update_hax_unit(filename: str) -> None:
    try:
        with open(filename) as f:
            contents = f.readlines()
        new_contents = HaxUnitTransformer().transform(contents)
        save(filename, '\n'.join(new_contents))
    except Exception as e:
        raise RuntimeError('Failed to update hax systemd unit: ' + str(e))


@func_log(func_enter, func_leave)
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
        save(filename, generate_cdf(url))
        update_hax_unit('/usr/lib/systemd/system/hare-hax.service')
        generate_config(url, filename)
        stop_consul_blocking(consul_starter)
    except Exception as error:
        if consul_starter:
            stop_consul_blocking(consul_starter)
        raise RuntimeError(f'Error performing configuration : {error}')


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


def check_parsed_command(cmd):
    if not hasattr(cmd, 'func'):
        raise RuntimeError('Error: No valid command passed.'
                           'Please check "--help"')


def create_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Configure hare settings')
    subparser = p.add_subparsers()

    parser = add_service_argument(
        add_subcommand(subparser,
                       'post_install',
                       help_str='Validates installation',
                       handler_fn=post_install))
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

    add_service_argument(sb_sub_parser)

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
    return p


def main():
    try:
        inject.configure(di_configuration)
        p = create_parser()
        parsed = p.parse_args(sys.argv[1:])

        setup_logging(parsed.config[0])

        check_parsed_command(parsed)
        parsed.func(parsed)
    except Exception as e:
        logging.error(str(e))
        logging.debug('Exiting with FAILED result', exc_info=True)
        exit(1)


if __name__ == '__main__':
    main()
