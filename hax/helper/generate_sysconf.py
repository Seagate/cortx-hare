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
# Module for Hare to create motr and s3server environment files.

from typing import Any, Dict, List, NamedTuple, Optional, Union
from hax.util import repeat_if_fails, KVAdapter
from hax.types import Fid, ObjT
import logging
import os
import re
from helper.exec import Executor, Program
import simplejson
import fileinput


def reload_consul():
    executor = Executor()
    logging.debug('Reloading consul')
    executor.run(Program([
        'consul', 'reload'
    ]))


class Service(NamedTuple):
    id: str
    name: str
    address: str
    port: int
    checks: List[Dict[str, Any]]


class KVFile:

    """Helper to fetch data from Hare-Motr configuration key values file."""

    def __init__(self, kv_file: str, node: str) -> None:
        """Loads Hare-Motr configuration in memory to generate sysconfig."""
        self.kv_file = kv_file
        self.kv_data = self._read_file()
        self.node = node

    def _read_file(self) -> List[Dict[str, Any]]:
        with open(self.kv_file) as consul_kv_file:
            data = simplejson.load(consul_kv_file)
        return data

    def get_service_ids(self, svc_name: str) -> List[str]:
        """
        Returns the service id by its name assuming that it runs at the
        current node.

        Examples of the key that will match:
            m0conf/nodes/srvnode1/processes/6/services/ha
        """
        regex = re.compile(f'^m0conf/nodes/{self.node}\\/processes/([0-9]+)'
                           f'/services/{svc_name}$')
        keys = []
        for key in self.kv_data:
            match_result = re.match(regex, key['key'])
            if not match_result:
                continue
            keys.append(match_result.group(1))
        return keys

    def get_service_ep(self, proc_id: str) -> Optional[str]:
        """
        Returns the service endpoint from the given process id assuming that it
        runs at the current node.

        Examples of the key that will match:
            key = m0conf/nodes/srvnode-1/processes/10/endpoint
            value = inet:tcp:10.230.246.59@3001
        """
        regex = re.compile(
            f'm0conf/nodes/{self.node}/processes/{proc_id}/endpoint')
        for key in self.kv_data:
            match_result = re.match(regex, key['key'])
            if not match_result:
                continue
            return key['value']
        return None

    def get_ios_meta_data(self, proc_id: str) -> Optional[str]:
        """
        Returns the metadata path for a given ioservice fid.

        Examples of the key that will match:
            key = m0conf/nodes/srvnode-1.data.private/processes/10/meta_data
            value = /dev/vg_srvnode-1_md1/lv_raw_md1
        """
        regex = re.compile(
            f'm0conf/nodes/{self.node}/processes/{proc_id}/meta_data')
        for key in self.kv_data:
            match_result = re.match(regex, key['key'])
            if not match_result:
                continue
            return key['value']
        return None

    def get_profile_fid(self) -> Optional[str]:
        regex = re.compile('m0conf/profiles/')
        for key in self.kv_data:
            match_result = re.match(regex, key['key'])
            if not match_result:
                continue
            return key['key'].split('/')[-1]
        return None


class ConsulKV:
    """
    Helper class to fetch data from consul kv.
    """

    def __init__(self, node: str) -> None:
        """Initializes the Consul KV adapter."""
        self.kv = KVAdapter()
        self.node = node

    @repeat_if_fails()
    def get_service_ids(self, svc_name: str) -> List[str]:
        """
        Returns the service id by its name assuming that it runs at the
        current node.

        Examples of the key that will match:
            m0conf/nodes/srvnode1/processes/6/services/ha
        """
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        regex = re.compile(f'^m0conf/nodes/{self.node}\\/processes/([0-9]+)'
                           f'/services/{svc_name}$')
        keys = []
        for key in node_items:
            match_result = re.match(regex, key['Key'])
            if not match_result:
                continue
            keys.append(match_result.group(1))
        return keys

    @repeat_if_fails()
    def get_service_ep(self, proc_id: str) -> Optional[str]:
        """
        Returns the service endpoint from the given process id assuming that it
        runs at the current node.

        Examples of the key that will match:
            key = m0conf/nodes/srvnode-1/processes/10/endpoint
            value = inet:tcp:10.230.246.59@3001
        """
        key = self.kv.kv_get(
            f'm0conf/nodes/{self.node}/processes/{proc_id}/endpoint')
        if key:
            return key['Value'].decode("utf-8")
        return None

    @repeat_if_fails()
    def get_ios_meta_data(self, proc_id: str) -> Optional[str]:
        """
        Returns the metadata path for a given ioservice fid.

        Examples of the key that will match:
            key = m0conf/nodes/srvnode-1.data.private/processes/10/meta_data
            value = /dev/vg_srvnode-1_md1/lv_raw_md1
        """
        key = self.kv.kv_get(
            f'm0conf/nodes/{self.node}/processes/{proc_id}/meta_data')
        if key:
            return key['Value'].decode("utf-8")
        return None

    @repeat_if_fails()
    def get_profile_fid(self) -> str:
        profile_key = self.kv.kv_get('m0conf/profiles/', keys=True)
        assert profile_key
        # Get the first profile fid
        return profile_key[0].split('/')[-1]


class Generator:
    """
    Generates system configuration files for consul-agent, motr and
    s3 services.
    """

    def __init__(self, node: str, hare_conf_dir: str,
                 kv_file: Optional[str] = None):
        # Based on the kv_file input, we choose whether to fetch data from
        # kv file or consul kv.
        self.provider: Union[KVFile, ConsulKV] = KVFile(
            kv_file=kv_file, node=node) if kv_file else ConsulKV(node)
        self.node = node
        if not os.path.isdir(hare_conf_dir):
            raise FileNotFoundError(f'{hare_conf_dir} does not exist.')
        self.hare_conf_dir = hare_conf_dir + '/'
        self.sysconf_dir = 'sysconfig/'

    def _write_file(self, filepath: str, contents: str) -> None:
        logging.debug('Writing to file %s', filepath)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(contents)

    def generate_confd(self, svc_id: str, hax_ep: str, motr_conf_dir: str):
        fid = Fid(ObjT.PROCESS.value, int(svc_id))
        ep = self.provider.get_service_ep(svc_id)
        filename = f'm0d-{fid}'
        contents = (f"MOTR_M0D_EP='{ep}'\n"
                    f"MOTR_HA_EP='{hax_ep}'\n"
                    f"MOTR_PROCESS_FID='{fid}'\n"
                    f"MOTR_CONF_XC='{motr_conf_dir}/confd.xc'\n")
        self._write_file(motr_conf_dir + self.sysconf_dir + filename,
                         contents)

    def generate_ios(self, svc_id: str, hax_ep: str, motr_conf_dir: str):
        fid = Fid(ObjT.PROCESS.value, int(svc_id))
        ep = self.provider.get_service_ep(svc_id)
        meta_data = self.provider.get_ios_meta_data(svc_id)
        filename = f'm0d-{fid}'
        contents = (f"MOTR_M0D_EP='{ep}'\n"
                    f"MOTR_HA_EP='{hax_ep}'\n"
                    f"MOTR_PROCESS_FID='{fid}'\n")
        if meta_data:
            contents += f'MOTR_BE_SEG_PATH={meta_data}\n'
        self._write_file(motr_conf_dir + self.sysconf_dir + filename,
                         contents)

    def generate_s3(self, svc_id: str, hax_ep: str, s3_port: int,
                    s3_conf_dir: str):
        profile_fid = self.provider.get_profile_fid()
        fid = Fid(ObjT.PROCESS.value, int(svc_id))
        ep = self.provider.get_service_ep(svc_id)
        filename = f's3server-{fid}'
        contents = (f"MOTR_PROFILE_FID={profile_fid}\n"
                    f"MOTR_S3SERVER_EP='{ep}'\n"
                    f"MOTR_HA_EP='{hax_ep}'\n"
                    f"MOTR_PROCESS_FID='{fid}'\n"
                    f"MOTR_S3SERVER_PORT={s3_port}\n")
        self._write_file(s3_conf_dir + self.sysconf_dir + filename,
                         contents)

    def generate_sysconfig(self, motr_conf_dir: str, s3_conf_dir: str, ):
        s3_port = 28071

        IDs = self.get_all_svc_ids()

        hax_ep = self.provider.get_service_ep(IDs['HAX_ID'][0])
        if not hax_ep:
            raise RuntimeError('Cannot get hax endpoint.')
        for x in IDs['CONFD_IDs']:
            self.generate_confd(x, hax_ep, motr_conf_dir + '/')

        for x in IDs['IOS_IDs']:
            self.generate_ios(x, hax_ep, motr_conf_dir + '/')

        for x in IDs['S3_IDs']:
            self.generate_s3(x, hax_ep, s3_port, s3_conf_dir + '/')
            s3_port += 1

    def append_svcs_to_file(self, svcs, conf_file):
        with open(conf_file) as consul_conf_file:
            data = simplejson.load(consul_conf_file)
        data['services'] = svcs
        self._write_file(conf_file,
                         simplejson.dumps(data, indent=2, for_json=True))

    def get_service_ipaddr(self, ep: str) -> str:
        return ep.split('@')[0]

    def append_ipaddr_to_file(self, hax_ep: str, conf_file: str):
        ipaddr = self.get_service_ipaddr(hax_ep)
        regex = re.compile(r'(https?://)localhost')
        # in-place filtering: if the keyword argument inplace=True is
        # passed to FileInput constructor, the file is moved to a
        # backup file and standard output is directed to the input
        # file that is passed to the constructor.
        # https://docs.python.org/3/library/fileinput.html#fileinput.FileInput
        with fileinput.FileInput(conf_file, inplace=True,
                                 backup='.bak') as file:
            for line in file:
                print(re.sub(regex, rf'\g<1>{ipaddr}', line), end='')

    def get_service_addr(self, ep: str) -> str:
        return ep.rsplit('@', 1)[0]

    def get_service_port(self, ep: str) -> int:
        return int(ep.rsplit('@', 1)[1])

    def prepare_svc(self, svc_id: str, name: str):
        ep = self.provider.get_service_ep(svc_id)
        if not ep:
            raise RuntimeError('Cannot get service endpoint.')
        addr = self.get_service_addr(ep)
        port = self.get_service_port(ep)

        checks: Dict[str, Any] = {}
        checks['args'] = ['/opt/seagate/cortx/hare/libexec/check-service']
        checks['interval'] = '1s'
        checks['status'] = 'warning'
        # get svc checks args as per svc name
        if name == 'hax':
            checks['args'].append('--hax')
        elif name in ('confd', 'ios'):
            fid = Fid(ObjT.PROCESS.value, int(svc_id))
            checks['args'].extend(['--fid', str(fid)])
        elif name == 's3service':
            fid = Fid(ObjT.PROCESS.value, int(svc_id))
            s3svc = 's3server@' + str(fid)
            checks['args'].extend(['--svc', s3svc])
        return Service(id=svc_id, name=name, address=addr, port=port,
                       checks=[checks])

    def update_consul_conf(self):

        IDs = self.get_all_svc_ids()

        mode = 'server' if IDs['CONFD_IDs'] else 'client'
        conf_file = (f'{self.hare_conf_dir}/consul-{mode}-conf/'
                     f'consul-{mode}-conf.json')

        svcs = []
        for x in IDs['HAX_ID']:
            svcs.append(self.prepare_svc(x, 'hax'))

        for x in IDs['CONFD_IDs']:
            svcs.append(self.prepare_svc(x, 'confd'))

        for x in IDs['IOS_IDs']:
            svcs.append(self.prepare_svc(x, 'ios'))

        for x in IDs['S3_IDs']:
            svcs.append(self.prepare_svc(x, 's3service'))

        self.append_svcs_to_file(svcs, conf_file)

        ep = self.provider.get_service_ep(IDs['HAX_ID'][0])
        if not ep:
            raise RuntimeError('Cannot get hax endpoint.')
        self.append_ipaddr_to_file(ep, conf_file)

    def get_all_svc_ids(self) -> Dict[str, List[str]]:

        IDs: Dict[str, List[str]] = {}
        IDs['HAX_ID'] = self.provider.get_service_ids('ha')
        if not IDs['HAX_ID']:
            raise RuntimeError(
                'Cannot get information about Hax from Consul for this host '
                f'{self.node}. Please verify that the host name '
                'matches the one stored in the Consul KV.')
        IDs['CONFD_IDs'] = self.provider.get_service_ids('confd')
        IDs['IOS_IDs'] = self.provider.get_service_ids('ios')
        IDs['S3_IDs'] = self.provider.get_service_ids('m0_client_s3')
        return IDs

    def get_svc_fids(self, svc_name: str) -> List[str]:
        IDs = self.get_all_svc_ids()
        id_map = {
            'hax': IDs['HAX_ID'],
            'confd': IDs['CONFD_IDs'],
            'ios': IDs['IOS_IDs'],
            's3': IDs['S3_IDs']
        }
        return [str(Fid(ObjT.PROCESS.value, int(x)))
                for x in id_map[svc_name]]
