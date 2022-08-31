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

import subprocess
import json
import io
import os
import logging
from typing import List
from functools import wraps
from distutils.dir_util import copy_tree
import shutil
from time import sleep
from urllib.parse import urlparse

from cortx.utils.cortx import Const
from hax.util import repeat_if_fails, KVAdapter
from helper.exec import Program, Executor

from hare_mp.store import ValueProvider
from hare_mp.types import Disk, DList, Maybe, Text

LOG_DIR_EXT = '/hare/log/'


def func_enter(func):
    """Logs function entry point."""
    func_name = func.__qualname__
    func_line = func.__code__.co_firstlineno
    func_filename = func.__code__.co_filename
    logging.info('Entering %s at line %d in file %s', func_name, func_line,
                 func_filename)


def func_leave(func):
    """Logs function exit point."""
    logging.info('Leaving %s', func.__qualname__)


def func_log(before=func_enter, after=func_leave):
    def decorate(f):
        @wraps(f)
        def call(*args, **kwargs):
            before(f)
            result = f(*args, **kwargs)
            after(f)
            return result
        return call
    return decorate


class Utils:
    def __init__(self, provider: ValueProvider):
        """Initializes value provider like ConfStore."""
        self.provider = provider
        self.kv = KVAdapter()

    @func_log(func_enter, func_leave)
    def get_hostname(self, machine_id: str) -> str:
        """
        Returns the hostname of the given machine_id according to the given
        ConfStore (ValueProvider).
        """

        store = self.provider
        hostname = store.get(
            f'node>{machine_id}>network>data>private_fqdn', allow_null=True)
        return hostname or store.get(f'node>{machine_id}>hostname')

    @func_log(func_enter, func_leave)
    def get_local_hostname(self) -> str:
        """
        Retrieves the machine-id of the node where the code runs and fetches
        its hostname from the ConfStore (ValueProvider).
        """
        store = self.provider
        machine_id = store.get_machine_id()
        return self.get_hostname(machine_id)

    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def save_node_facts(self):
        hostname = self.get_local_hostname()
        cmd = ['facter', '--json', 'processorcount', 'memorysize_mb']
        node_facts = execute(cmd)
        self.kv.kv_put(f'{hostname}/facts', node_facts)

    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def get_node_facts(self):
        hostname = self.get_local_hostname()
        node_facts = None
        node_facts_val = None
        while (not node_facts or node_facts is None):
            try:
                node_facts = self.kv.kv_get(f'{hostname}/facts')
                node_facts_val = json.loads(node_facts['Value'])
            except TypeError:
                logging.info('%s facts not available yet, retrying...',
                             hostname)
                sleep(2)
                continue
        return node_facts_val

    @func_log(func_enter, func_leave)
    def get_data_devices(self, machine_id: str, cvg: int) -> DList[Text]:
        data_devices = []
        num_data = int(self.provider.get(
            f'node>{machine_id}>cvg[{cvg}]>devices>num_data'))
        for i in range(num_data):
            data_devices.append(Text(self.provider.get(
                f'node>{machine_id}>'
                f'cvg[{cvg}]>devices>data[{i}]')))
        return DList(data_devices, 'List Text')

    @func_log(func_enter, func_leave)
    def get_log_devices(self, machine_id: str, cvg: int) -> DList[Text]:
        log_devices = DList(
            [Text(device) for device in self.provider.get(
                f'node>{machine_id}>'
                f'cvg[{cvg}]>devices>log',
                allow_null=True) or []], 'List Text')
        return log_devices

    @func_log(func_enter, func_leave)
    def _get_drive_info_form_os(self, path: str) -> Disk:
        drive_size = 0
        with open(path, 'rb') as f:
            drive_size = f.seek(0, io.SEEK_END)
        return Disk(path=Maybe(Text(path), 'Text'),
                    size=Maybe(drive_size, 'Natural'),
                    blksize=Maybe(os.stat(path).st_blksize, 'Natural'))

    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def _save_drive_info(self, path: str):
        disk: Disk = self._get_drive_info_form_os(path)
        hostname = self.get_local_hostname()
        drive_info = json.dumps({'path': disk.path.get().s,
                                 'size': int(disk.size.get()),
                                 'blksize': int(disk.blksize.get())})
        disk_key = path.strip('/')
        self.kv.kv_put(f'{hostname}/drives/{disk_key}', drive_info)

    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def save_log_path(self):
        hostname = self.get_local_hostname()
        machine_id = self.provider.get_machine_id()
        log_key = self.provider.get('cortx>common>storage>log')
        log_path = log_key + LOG_DIR_EXT + machine_id
        self.kv.kv_put(f'{hostname}/log_path', log_path)

    @func_log(func_enter, func_leave)
    def is_motr_io_present(self, machine_id: str) -> bool:
        """
        Returns True if motr component is present in the components list
        for the given node>{machine_id}.
        """
        return self.is_component_and_service(machine_id,
                                             Const.COMPONENT_MOTR.value,
                                             Const.SERVICE_MOTR_IO.value)

    @func_log(func_enter, func_leave)
    def is_component(self, machine_id: str, name: str) -> bool:
        """
        Returns True if the given component is present in the components
        list for the given node>{machine_id} according to the
        ConfStore (ValueProvider).
        """
        num_comp = int(self.provider.get(f'node>{machine_id}>num_components'))
        found = False
        for i in range(num_comp):
            comp_name = self.provider.get(
                f'node>{machine_id}>components[{i}]>name')
            if(comp_name == name):
                found = True
                break
        return found

    @func_log(func_enter, func_leave)
    def is_component_and_service(self, machine_id: str,
                                 comp_name: str, svc_name: str) -> bool:
        """
        Returns True if the given service and component is present in the
        components list for the given node>{machine_id} according to the
        ConfStore (ValueProvider).
        """
        return self.is_component(machine_id, comp_name) and \
            self.is_service(machine_id, svc_name)

    @func_log(func_enter, func_leave)
    def is_component_or_service(self, machine_id: str, name: str) -> bool:
        """
        Returns True if the given service or component is present in the
        components list for the given node>{machine_id} according to the
        ConfStore (ValueProvider).
        """
        return self.is_component(machine_id, name) or \
            self.is_service(machine_id, name)

    @func_log(func_enter, func_leave)
    def is_service(self, machine_id: str, svc_name: str) -> bool:
        """
        Returns True if the given service is present in the components
        list for the given node>{machine_id} according to the
        ConfStore (ValueProvider).
        """
        found: bool = False
        num_comp = int(self.provider.get(f'node>{machine_id}>num_components'))
        for i in range(num_comp):
            num_svc = self.provider.get(
                f'node>{machine_id}>components[{i}]>num_services',
                allow_null=True)
            if num_svc:
                for j in range(int(num_svc)):
                    service = self.provider.get(
                        f'node>{machine_id}>components[{i}]>services[{j}]')
                    if(service == svc_name):
                        found = True
                        break
        return found

    @func_log(func_enter, func_leave)
    def save_drives_info(self):
        machine_id = self.provider.get_machine_id()
        if(self.is_motr_io_present(machine_id)):
            num_cvg = int(self.provider.get(f'node>{machine_id}>num_cvg'))
            for cvg in range(num_cvg):
                data_devs = self.get_data_devices(machine_id, cvg)
                for dev_path in data_devs.value:
                    self._save_drive_info(dev_path.s)
                log_devs = self.get_log_devices(machine_id, cvg)
                if log_devs:
                    for dev_path in log_devs.value:
                        self._save_drive_info(dev_path.s)

    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def get_drive_info_from_consul(self, path: Text, machine_id: str) -> Disk:
        hostname = self.get_hostname(machine_id)
        disk_path = json.loads(str(path)).lstrip(os.sep)
        drive_data = None
        drive_info = None
        while (not drive_data or drive_data is None):
            try:
                drive_data = self.kv.kv_get(f'{hostname}/drives/{disk_path}')
                drive_info = json.loads(drive_data['Value'])
            except TypeError:
                logging.info('%s details are not available yet, retrying...',
                             disk_path)
                sleep(2)
                continue
        return (Disk(path=Maybe(path, 'Text'),
                     size=Maybe(drive_info['size'], 'Natural'),
                     blksize=Maybe(drive_info['blksize'], 'Natural')))

    @func_log(func_enter, func_leave)
    def get_data_drives_info_for(self, cvg: int,
                                 machine_id: str) -> DList[Disk]:
        data_devs = self.get_data_devices(machine_id, cvg)
        return DList([self.get_drive_info_from_consul(dev_path, machine_id)
                      for dev_path in data_devs.value], 'List Disk')

    @func_log(func_enter, func_leave)
    def get_log_drives_info_for(self, cvg: int,
                                machine_id: str) -> DList[Disk]:
        data_devs = self.get_log_devices(machine_id, cvg)
        return DList([self.get_drive_info_from_consul(dev_path, machine_id)
                      for dev_path in data_devs.value], 'List Disk')

    @func_log(func_enter, func_leave)
    def import_kv(self, conf_dir_path: str):
        with open(f'{conf_dir_path}/consul-kv.json') as f:
            data = json.load(f)
            for item in data:
                item_data = json.loads(json.dumps(item))
                self.kv.kv_put(item_data['key'],
                               str(item_data['value']))

    @func_log(func_enter, func_leave)
    def copy_conf_files(self, conf_dir_path: str):
        machine_id = self.provider.get_machine_id()
        global_config_path = self.provider.get('cortx>common>storage>local')

        dest_motr = f'{global_config_path}/motr/sysconfig/{machine_id}'
        os.makedirs(dest_motr, exist_ok=True)

        cmd = ['/opt/seagate/cortx/hare/libexec/node-name',
               '--conf-dir', conf_dir_path]
        node_name = execute(cmd)

        copy_tree(f'{conf_dir_path}/sysconfig/motr/{node_name}', dest_motr)

        with open(f'{conf_dir_path}/consul-kv.json') as f:
            data = json.load(f)
            for item in data:
                item_data = json.loads(json.dumps(item))
                if item_data['key'] == 'm0_client_types':
                    m0_client_types = item_data['value']
                    break

        for client_type in json.loads(m0_client_types):
            src = f'{conf_dir_path}/sysconfig/{client_type}/{node_name}'
            dest = f'{global_config_path}/{client_type}/sysconfig/{machine_id}'
            os.makedirs(dest, exist_ok=True)
            copy_tree(src, dest)

        shutil.copyfile(
            f'{conf_dir_path}/confd.xc',
            f'{dest_motr}/confd.xc')

    @func_log(func_enter, func_leave)
    def copy_consul_files(self, conf_dir_path: str, mode: str):
        shutil.copyfile(
            f'{conf_dir_path}/consul-{mode}-conf/consul-{mode}-conf.json',
            f'{conf_dir_path}/consul/config/consul-{mode}-conf.json')

    @func_log(func_enter, func_leave)
    def stop_hare(self):
        self.hare_stop = True

    @func_log(func_enter, func_leave)
    def is_hare_stopping(self) -> bool:
        return self.hare_stop

    @func_log(func_enter, func_leave)
    def get_transport_type(self) -> str:
        transport_type = self.provider.get(
            'cortx>motr>transport_type',
            allow_null=True)
        if transport_type is None:
            return 'libfab'
        return transport_type

    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def save_config_path(self, path: str):
        self.kv.kv_put('config_path', path)

    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def save_ssl_config(self):
        http_protocol = 'http'
        num_ep = int(self.provider.get('cortx>hare>hax>num_endpoints'))
        for i in range(num_ep):
            url = self.provider.get(f'cortx>hare>hax>endpoints[{i}]')
            scheme = urlparse(url).scheme
            if scheme in ('http', 'https'):
                http_protocol = scheme
                break
        cert_path = self.provider.get('cortx>common>security>ssl_certificate')
        ssl_hax = json.dumps({
            'http_protocol': http_protocol,
            'cert_path': cert_path,
            'key_path': cert_path,
        })
        self.kv.kv_put('ssl/hax', ssl_hax)

    # Provisioner will be generating node_group from each data pod and place
    # gconf copy into consul. Hence from consul for all data pods node_group
    # value will be available.
    @func_log(func_enter, func_leave)
    @repeat_if_fails()
    def get_node_group(self, machine_id: str, allow_null: bool = False):
        key = f'conf/node>{machine_id}>node_group'
        node_group = self.kv.kv_get(key, allow_null=allow_null)
        if node_group:
            return node_group['Value'].decode()
        return None


class LogWriter:
    def __init__(self, logger: logging.Logger, logging_handler):
        """Initialize LogWriter object with Logger and LoggingHandler obj."""
        self.logger = logger
        self.logging_handler = logging_handler

    def write(self, msg: str):
        self.logger.log(logging.INFO, msg)

    def flush(self):
        pass

    def fileno(self):
        return self.logging_handler.stream.fileno()


def execute(cmd: List[str], env=None) -> str:
    p = Program(cmd)
    out = Executor().run(p, env=env)
    return out


def execute_no_communicate(cmd: List[str], env=None,
                           working_dir: str = '/var/log/cortx/hare',
                           out_file=subprocess.PIPE):
    process = subprocess.Popen(cmd,
                               stdin=subprocess.PIPE,
                               stdout=out_file,
                               stderr=out_file,
                               cwd=working_dir,
                               close_fds=False,
                               encoding='utf8',
                               env=env)
    if process.returncode:
        raise Exception(
            f'Command {cmd} exited with error code {process.returncode}. ')

    return process
