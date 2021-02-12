#!/usr/bin/env python3
#
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

import logging
import re
import threading
import argparse
import subprocess
from queue import Queue
from socket import gethostname
from typing import Dict, List, NamedTuple

from consul import Consul, ConsulException
from requests.exceptions import RequestException
from urllib3.exceptions import HTTPError
from hax.exception import HAConsistencyException
from hax.util import ConsulUtil

Process = NamedTuple('Process', [('node', str), ('consul_name', str),
                                 ('systemd_name', str), ('fidk', int),
                                 ('status', str), ('is_local', bool)])
shutdown_sequence = ('s3service', 'ios', 'confd', 'hax', 'consul')


def setup_logging():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increase output verbosity",
                        action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')


def processfid2str(fidk: int) -> str:
    return '{:#x}:{:#x}'.format(ord('r') << 56 | 1, fidk)


def get_kv(cns: Consul, key: str) -> str:
    try:
        kv: Dict[str, bytes] = cns.kv.get(key)[1]
        return kv['Value'].decode() if kv and kv['Value'] is not None else ''
    except (ConsulException, HTTPError, RequestException) as e:
        raise HAConsistencyException('Could not access Consul KV')\
            from e


def get_systemd_name(fidk: int, svc_name: str) -> str:
    if svc_name == 'hax':
        return 'hare-hax'
    elif svc_name == 's3service':
        return 's3server@' + processfid2str(fidk)
    else:
        return 'm0d@' + processfid2str(fidk)


def processes_node(cns: Consul, node_name: str) -> Dict[str, List[Process]]:
    """Processes grouped by Consul service name."""
    try:
        processes: Dict[str, List[Process]] = {}
        cns_util = ConsulUtil(raw_client=cns)
        is_local = node_name == cns_util.get_local_nodename()

        for node in cns.catalog.nodes()[1]:
            if node_name != node['Node']:
                continue

            for svc in cns.health.node(node['Node'])[1]:
                svc_name = svc['ServiceName']
                if svc_name:
                    fidk = int(svc['ServiceID'])
                    processes.setdefault(svc_name, []).append(
                        Process(node=node['Node'],
                                consul_name=svc_name,
                                systemd_name=get_systemd_name(fidk, svc_name),
                                fidk=fidk,
                                is_local=is_local,
                                status=svc['Status']))
            consul_status = 'passing' if consul_is_active_at(node['Node']) \
                else 'offline'
            processes.setdefault('consul', []).append(
                Process(node=node['Node'],
                        consul_name='consul',
                        systemd_name='hare-consul-agent',
                        fidk=0,
                        is_local=is_local,
                        status=consul_status))
        return processes
    except (ConsulException, HTTPError, RequestException) as e:
        raise HAConsistencyException('Could not access Consul services')\
            from e


def processes_by_consul_svc_name(cns: Consul) -> Dict[str, List[Process]]:
    """Processes grouped by Consul service name."""
    try:
        cns_util = ConsulUtil(raw_client=cns)

        processes: Dict[str, List[Process]] = {}
        for node in cns.catalog.nodes()[1]:
            is_local = node['Node'] == cns_util.get_local_nodename()
            for svc in cns.health.node(node['Node'])[1]:
                svc_name = svc['ServiceName']
                if svc_name:
                    fidk = int(svc['ServiceID'])
                    processes.setdefault(svc_name, []).append(
                        Process(node=node['Node'],
                                consul_name=svc_name,
                                systemd_name=get_systemd_name(fidk, svc_name),
                                fidk=fidk,
                                is_local=is_local,
                                status=svc['Status']))
            consul_status = 'passing' if consul_is_active_at(node['Node']) \
                else 'offline'
            processes.setdefault('consul', []).append(
                Process(node=node['Node'],
                        consul_name='consul',
                        systemd_name='hare-consul-agent',
                        fidk=0,
                        is_local=is_local,
                        status=consul_status))
        return processes
    except (ConsulException, HTTPError, RequestException) as e:
        raise HAConsistencyException('Could not access Consul services')\
            from e


def is_localhost(hostname: str) -> bool:
    name = gethostname()
    return hostname in ('localhost', '127.0.0.1', name, f'{name}.local')


def is_fake_leader_name(leader: str) -> bool:
    return re.match(r'^elect[0-9]+$', leader) is not None


def ssh_prefix(hostname: str) -> str:
    assert hostname
    return '' if is_localhost(hostname) else f'ssh {hostname} '


def consul_is_active_at(hostname: str) -> bool:
    cmd = ssh_prefix(hostname) + \
        'sudo systemctl is-active --quiet hare-consul-agent'
    return subprocess.call(cmd, shell=True) == 0


def pcs_consul_is_active_at(hostname: str) -> bool:
    cmd = ssh_prefix(hostname) + \
        'sudo systemctl is-active --quiet hare-consul-agent*'
    return subprocess.call(cmd, shell=True) == 0


def exec_silent(cmd: str) -> bool:
    return subprocess.call(cmd, shell=True) == 0


def exec_custom(cmd: str) -> None:
    assert cmd
    if exec_silent(cmd):
        logging.info('OK')
    else:
        logging.error('**ERROR**')


def process_stop(proc: Process) -> None:
    if proc.status != 'passing':
        return
    label = f' ({proc.consul_name})' if proc.systemd_name.startswith('m0d@') \
        else ''
    logging.info(f'Stopping {proc.systemd_name}{label} at {proc.node}... ')
    ok = exec_silent('{}sudo systemctl stop --force {}'.format(
        ssh_prefix(proc.node), proc.systemd_name))
    if ok:
        logging.info(f'Stopped {proc.systemd_name}{label} at {proc.node}')
    else:
        logging.error(f'**ERROR** Failed to stop {proc.systemd_name}{label}'
                      f' at {proc.node}')


class StopProcess:
    def __init__(self, process: Process):
        self.process = process


class QuitMessage:
    pass


class Worker(threading.Thread):
    def __init__(self, queue: Queue):
        # [KN] We mark the thread as daemonic to make sure it will
        # exit as soon as the main thread exits.
        # That will make sure that the application shuts down on
        # SIGINT event (Ctrl-C)
        super().__init__(target=self._do_work, args=(queue, ), daemon=True)

    def _do_work(self, queue: Queue):
        logging.debug('Started thread')
        while True:
            msg = queue.get()
            if isinstance(msg, StopProcess):
                process_stop(msg.process)
            if isinstance(msg, QuitMessage):
                logging.debug('Exiting thread')
                return


def stop_parallel(process_list: List[Process], thread_count: int = 8) -> None:
    size = len(process_list)

    if not size:
        return
    q: Queue = Queue(maxsize=size)
    thread_count = min(thread_count, size)

    worker_pool: List[Worker] = [Worker(q) for i in range(thread_count)]

    for w in worker_pool:
        w.start()

    for proc in process_list:
        q.put(StopProcess(process=proc))
    for i in range(thread_count):
        q.put(QuitMessage())

    for worker in worker_pool:
        worker.join()
