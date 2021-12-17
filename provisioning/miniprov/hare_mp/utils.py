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
from typing import List, Dict, Any
from distutils.dir_util import copy_tree
import shutil

from cortx.utils.cortx import Const
from hax.util import repeat_if_fails, KVAdapter
from helper.exec import Program, Executor

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

    def is_motr_component(self, machine_id: str) -> bool:
        """
        Returns True if motr component is present in the components list
        for the given node>{machine_id} according to the
        ConfStore (ValueProvider).
        """
        comp_names = self.provider.get(f'node>{machine_id}>'
                                       f'components')
        for component in comp_names:
            if(component.get('name') == Const.COMPONENT_MOTR.value):
                rc = True
                break
            else:
                rc = False
        return rc

    def is_s3_component(self, machine_id: str) -> bool:
        """
        Returns True if s3 component is present in the components list
        for the given node>{machine_id} according to the
        ConfStore (ValueProvider).
        """
        comp_names = self.provider.get(f'node>{machine_id}>'
                                       f'components')
        for component in comp_names:
            if(component.get('name') == Const.COMPONENT_S3.value):
                rc = True
                break
            else:
                rc = False
        return rc

    def save_drives_info(self):
        machine_id = self.provider.get_machine_id()
        if(self.is_motr_component(machine_id)):
            cvgs_key: str = f'node>{machine_id}>storage>cvg'
            for cvg in range(len(self.provider.get(cvgs_key))):
                data_devs = self.get_data_devices(machine_id, cvg)
                for dev_path in data_devs.value:
                    self._save_drive_info(dev_path.s)

    @repeat_if_fails()
    def get_drive_info_from_consul(self, path: Text, machine_id: str) -> Disk:
        hostname = self.get_hostname(machine_id)
        disk_path = json.loads(str(path)).lstrip(os.sep)
        drive_data = self.kv.kv_get(f'{hostname}/{disk_path}')
        drive_info = json.loads(drive_data['Value'])
        return (Disk(path=Maybe(path, 'Text'),
                     size=Maybe(drive_info['size'], 'Natural'),
                     blksize=Maybe(drive_info['blksize'], 'Natural')))

    def get_drives_info_for(self, cvg: int, machine_id: str) -> DList[Disk]:
        data_devs = self.get_data_devices(machine_id, cvg)
        return DList([self.get_drive_info_from_consul(dev_path, machine_id)
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

    def copy_consul_files(self, conf_dir_path: str, mode: str):
        shutil.copyfile(
            f'{conf_dir_path}/consul-{mode}-conf/consul-{mode}-conf.json',
            f'{conf_dir_path}/consul/config/consul-{mode}-conf.json')

    def stop_hare(self):
        self.hare_stop = True

    def is_hare_stopping(self) -> bool:
        return self.hare_stop

    def get_io_nodes(self) -> List[str]:
        nodes: List[str] = []
        conf = self.provider
        machines: Dict[str, Any] = conf.get('node')
        # Query results into a list of keys where, Const.SERVICE_MOTR_IO
        # is found as one of the services under `services`.
        # e.g.
        # node>0b9cf99f07574422a45f9b61d2f5b746>components[1]>services[0]
        # node>0b9cf99f07574422a45f9b61d2f5b746>components[3]>services[0]
        services = conf.search_val('node', 'services',
                                   Const.SERVICE_MOTR_IO.value)
        for machine_id in machines.keys():
            result = list(filter(lambda svc: machine_id in svc, services))
            if result:
                nodes.append(conf.get(f'node>{machine_id}>hostname'))
        return nodes

    def get_transport_type(self) -> str:
        transport_type = self.provider.get(
            'cortx>motr>transport_type',
            allow_null=True)
        if transport_type is None:
            return 'libfab'
        return transport_type


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
