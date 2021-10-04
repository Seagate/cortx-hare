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
from distutils.dir_util import copy_tree
import shutil

from hax.util import repeat_if_fails, KVAdapter

from hare_mp.store import ValueProvider
from hare_mp.types import Disk, DList, Maybe, Text


class Utils:
    def __init__(self, provider: ValueProvider):
        self.provider = provider
        self.kv = KVAdapter()

    def get_hostname(self, machine_id: str) -> str:
        """
        Returns the hostname of the given machine_id according to the given
        ConfStore (ValueProvider).
        """

        store = self.provider
        hostname = store.get(
            f'node>{machine_id}>network>data>private_fqdn', allow_null=True)
        return hostname or store.get(f'node>{machine_id}>hostname')

    def get_local_hostname(self) -> str:
        """
        Retrieves the machine-id of the node where the code runs and fetches
        its hostname from the ConfStore (ValueProvider).
        """
        store = self.provider
        machine_id = store.get_machine_id()
        return self.get_hostname(machine_id)

    @repeat_if_fails()
    def save_node_facts(self):
        hostname = self.get_local_hostname()
        cmd = ['facter', '--json', 'processorcount', 'memorysize_mb']
        node_facts = execute(cmd)
        self.kv.kv_put(f'{hostname}/facts', node_facts)

    def get_node_facts(self):
        hostname = self.get_local_hostname()
        node_facts = self.kv.kv_get(f'{hostname}/facts')
        return json.loads(node_facts['Value'])

    def get_data_devices(self, machine_id: str, cvg: int) -> DList[Text]:
        data_devices = DList(
            [Text(device) for device in self.provider.get(
                f'node>{machine_id}>'
                f'storage>cvg[{cvg}]>devices>data')], 'List Text')
        return data_devices

    def _get_drive_info_form_os(self, path: str) -> Disk:
        drive_size = 0
        with open(path, 'rb') as f:
            drive_size = f.seek(0, io.SEEK_END)
        return Disk(path=Maybe(Text(path), 'Text'),
                    size=Maybe(drive_size, 'Natural'),
                    blksize=Maybe(os.stat(path).st_blksize, 'Natural'))

    @repeat_if_fails()
    def _save_drive_info(self, path: str):
        disk: Disk = self._get_drive_info_form_os(path)
        hostname = self.get_local_hostname()
        drive_info = json.dumps({'path': disk.path.get().s,
                                 'size': int(disk.size.get()),
                                 'blksize': int(disk.blksize.get())})
        disk_key = path.strip('/')
        self.kv.kv_put(f'{hostname}/{disk_key}', drive_info)

    def save_drives_info(self):
        machine_id = self.provider.get_machine_id()
        cvgs_key: str = f'node>{machine_id}>storage>cvg'
        for cvg in range(len(self.provider.get(cvgs_key))):
            data_devs = self.get_data_devices(machine_id, cvg)
            for dev_path in data_devs.value:
                self._save_drive_info(dev_path.s)

    @repeat_if_fails()
    def get_drive_info_from_consul(self, path: Text) -> Disk:
        hostname = self.get_local_hostname()
        disk_path = json.loads(str(path)).lstrip(os.sep)
        drive_data = self.kv.kv_get(f'{hostname}/{disk_path}')
        drive_info = json.loads(drive_data['Value'])
        return (Disk(path=Maybe(path, 'Text'),
                     size=Maybe(drive_info['size'], 'Natural'),
                     blksize=Maybe(drive_info['blksize'], 'Natural')))

    def get_drives_info_for(self, cvg: int) -> DList[Disk]:
        machine_id = self.provider.get_machine_id()
        data_devs = self.get_data_devices(machine_id, cvg)
        return DList([self.get_drive_info_from_consul(dev_path)
                      for dev_path in data_devs.value], 'List Disk')

    def import_kv(self, conf_dir_path: str):
        with open(f'{conf_dir_path}/consul-kv.json') as f:
            data = json.load(f)
            for item in data:
                item_data = json.loads(json.dumps(item))
                self.kv.kv_put(item_data['key'],
                               str(item_data['value']))

    def copy_conf_files(self, conf_dir_path: str):
        machine_id = self.provider.get_machine_id()
        global_config_path = self.provider.get('cortx>common>storage>local')

        dest_s3 = f'{global_config_path}/s3/sysconfig/{machine_id}'
        dest_motr = f'{global_config_path}/motr/sysconfig/{machine_id}'
        os.makedirs(dest_s3, exist_ok=True)
        os.makedirs(dest_motr, exist_ok=True)

        cmd = ['/opt/seagate/cortx/hare/libexec/node-name',
               '--conf-dir', conf_dir_path]
        node_name = execute(cmd)

        copy_tree(f'{conf_dir_path}/sysconfig/s3/{node_name}', dest_s3)
        copy_tree(f'{conf_dir_path}/sysconfig/motr/{node_name}', dest_motr)

        shutil.copyfile(
            f'{conf_dir_path}/confd.xc',
            f'{dest_motr}/confd.xc')

    def copy_consul_files(self, conf_dir_path: str):
        shutil.copyfile(
            f'{conf_dir_path}/consul-server-conf/consul-server-conf.json',
            f'{conf_dir_path}/consul/config/consul-server-conf.json')

    def stop_hare(self):
        self.hare_stop = True

    def is_hare_stopping(self) -> bool:
        return self.hare_stop


class LogWriter:
    def __init__(self, logger: logging.Logger, logging_handler):
        self.logger = logger
        self.logging_handler = logging_handler

    def write(self, msg: str):
        self.logger.log(logging.INFO, msg)

    def flush(self):
        pass

    def fileno(self):
        return self.logging_handler.stream.fileno()


def execute(cmd: List[str], env=None) -> str:
    process = subprocess.Popen(cmd,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               encoding='utf8',
                               env=env)
    out, err = process.communicate()
    if process.returncode:
        raise Exception(
            f'Command {cmd} exited with error code {process.returncode}. '
            f'Command output: {err}')

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
