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
from typing import List

from hax.util import repeat_if_fails, KVAdapter

from hare_mp.store import ValueProvider
from hare_mp.types import Disk, DList, Maybe, Text


class Utils:
    def __init__(self, provider: ValueProvider):
        self.provider = provider
        self.kv = KVAdapter()

    def get_hostname(self) -> str:
        machine_id = self.provider.get_machine_id()
        hostname = self.provider.get(
            f'server_node>{machine_id}>network>data>private_fqdn')
        return hostname

    @repeat_if_fails()
    def save_node_facts(self):
        hostname = self.get_hostname()
        cmd = ['facter', '--json', 'processorcount', 'memorysize_mb']
        node_facts = execute(cmd)
        self.kv.kv_put(f'{hostname}/facts', node_facts)

    def get_node_facts(self):
        hostname = self.get_hostname()
        node_facts = self.kv.kv_get(f'{hostname}/facts')
        return json.loads(node_facts['Value'])

    def get_data_devices(self, machine_id: str, cvg: int) -> DList[Text]:
        data_devices = DList(
            [Text(device) for device in self.provider.get(
                f'server_node>{machine_id}>'
                f'storage>cvg[{cvg}]>data_devices')], 'List Text')
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
        hostname = self.get_hostname()
        drive_info = json.dumps({'path': disk.path.get().s,
                                 'size': int(disk.size.get()),
                                 'blksize': int(disk.blksize.get())})
        disk_key = path.strip('/')
        self.kv.kv_put(f'{hostname}/{disk_key}', drive_info)

    def save_drives_info(self):
        machine_id = self.provider.get_machine_id()
        cvgs_key: str = f'server_node>{machine_id}>storage>cvg'
        for cvg in range(len(self.provider.get(cvgs_key))):
            data_devs = self.get_data_devices(machine_id, cvg)
            for dev_path in data_devs.value:
                self._save_drive_info(dev_path.s)

    @repeat_if_fails()
    def get_drive_info_from_consul(self, path: Text) -> Disk:
        hostname = self.get_hostname()
        disk_path = json.loads(str(path)).lstrip(os.sep)
        drive_data = self.kv.kv_get(f'{hostname}/{disk_path}')
        drive_info = json.loads(drive_data['Value'])
        return (Disk(path=Maybe(path, 'Text'),
                     size=Maybe(drive_info['size'], 'Natural'),
                     blksize=Maybe(drive_info['blksize'], 'Natural')))

    def get_drives_info(self) -> DList[Disk]:
        machine_id = self.provider.get_machine_id()
        cvgs_key: str = f'server_node>{machine_id}>storage>cvg'
        for cvg in range(len(self.provider.get(cvgs_key))):
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
