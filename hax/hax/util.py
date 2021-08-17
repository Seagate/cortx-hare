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

import json
import logging
import os
import re
from base64 import b64encode
from functools import wraps
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Callable
from hax.log import TRACE
from threading import Event
from time import sleep

import simplejson
from consul import Consul, ConsulException
from consul.base import ClientError
from requests.exceptions import RequestException
from urllib3.exceptions import HTTPError

from hax.exception import HAConsistencyException, InterruptedException
from hax.types import (ConfHaProcess, Fid, FsStatsWithTime,
                       ObjT, ServiceHealth, Profile, m0HaProcessEvent,
                       m0HaProcessType, KeyDelete, HaNoteStruct,
                       m0HaObjState)

__all__ = ['ConsulUtil', 'create_process_fid', 'create_service_fid',
           'create_sdev_fid', 'create_drive_fid']

LOG = logging.getLogger('hax')

# XXX What is the difference between `ip_addr` and `address`?
# The names are hard to discern.
ServiceData = NamedTuple('ServiceData', [('node', str), ('fid', Fid),
                                         ('ip_addr', str), ('address', str)])

FidWithType = NamedTuple('FidWithType', [('fid', Fid), ('service_type', str)])


MotrConsulProcInfo = NamedTuple('MotrConsulProcInfo', [('proc_status', str),
                                                       ('proc_type', str)])

MotrConsulProcStatus = NamedTuple('MotrConsulProcStatus', [(
                                        'consul_svc_status', str),
                                        ('consul_motr_proc_status', str)])

MotrProcStatusLocalRemote = NamedTuple('MotrProcStatusLocalRemote', [(
                                'motr_proc_status_local', ServiceHealth),
                                ('motr_proc_status_remote', ServiceHealth)])


def mkServiceData(service: Dict[str, Any]) -> ServiceData:
    return ServiceData(
        node=service['Node'],
        fid=mk_fid(
            ObjT.PROCESS,  # XXX s/PROCESS/SERVICE/ ?
            int(service['ServiceID'])),
        ip_addr=service['Address'],
        address='{}:{}'.format(service['ServiceAddress'],
                               service['ServicePort']))


def mk_fid(obj_t: ObjT, key: int) -> Fid:
    return Fid(obj_t.value, key)


def create_process_fid(key: int) -> Fid:
    return mk_fid(ObjT.PROCESS, key)


def create_service_fid(key: int) -> Fid:
    return mk_fid(ObjT.SERVICE, key)


def create_sdev_fid(key: int) -> Fid:
    return mk_fid(ObjT.SDEV, key)


def create_drive_fid(key: int) -> Fid:
    return mk_fid(ObjT.DRIVE, key)


def create_profile_fid(key: int) -> Fid:
    return mk_fid(ObjT.PROFILE, key)


# See enum m0_conf_ha_process_event in Motr source code.
ha_process_events = ('M0_CONF_HA_PROCESS_STARTING',
                     'M0_CONF_HA_PROCESS_STARTED',
                     'M0_CONF_HA_PROCESS_STOPPING',
                     'M0_CONF_HA_PROCESS_STOPPED')


ha_conf_obj_states = ('M0_NC_UNKNOWN',
                      'M0_NC_ONLINE',
                      'M0_NC_FAILED',
                      'M0_NC_TRANSIENT',
                      'M0_NC_REPAIR',
                      'M0_NC_REPAIRED',
                      'M0_NC_REBALANCE')


def repeat_if_fails(wait_seconds=5, max_retries=-1):
    """
    Ensures that the wrapped function gets re-invoked if
    HAConsistencyException gets raised. In other words, this wrapper
    makes the wrapped function repeatable.

    Parameters:

    wait_seconds - delay (in seconds) between the attempts. The delay
         applies after HAConsistencyException is raised.
    max_retries - how many attempts the wrapper will perform until finally
         re-raising the exception. -1 means 'repeat forever'.
    """
    def callable(f):
        @wraps(f)
        def wrapper(*args, **kwds):
            attempt_count = 0
            while (True):
                try:
                    return f(*args, **kwds)
                except HAConsistencyException as e:
                    attempt_count += 1
                    if max_retries >= 0 and attempt_count > max_retries:
                        LOG.warn(
                            'Function %s: Too many errors happened in a row '
                            '(max_retries = %d)', f.__name__, max_retries)
                        raise e
                    LOG.warn(f'Got HAConsistencyException: {e.message} while '
                             f'invoking function {f.__name__} '
                             f'(attempt {attempt_count}). The attempt will be '
                             f'repeated in {wait_seconds} seconds')
                    sleep(wait_seconds)

        return wrapper

    return callable


TxPutKV = NamedTuple('TxPutKV', [('key', str), ('value', str),
                                 ('cas', Optional[Any])])


def wait_for_event(event: Event, interval_sec) -> None:
    """
    Caller sleeps until the @event happens or the wait timesout after
    @interval_sec.
    """
    interrupted = event.wait(timeout=interval_sec)
    if interrupted:
        raise InterruptedException()


class KVAdapter:
    def __init__(self, cns: Optional[Consul] = None):
        self.cns = cns or Consul()

    def kv_get_raw(self, key: str, **kwargs) -> Tuple[int, Any]:
        """
        Helper method that should be used by default in this class whenver
        we want to invoke Consul.kv.get()
        """
        assert key
        try:
            return self.cns.kv.get(key, **kwargs)
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Could not access Consul KV') from e

    def kv_get(self, key: str, **kwargs) -> Any:
        return self.kv_get_raw(key, **kwargs)[1]

    def kv_put(self, key: str, data: str, **kwargs) -> bool:
        """
        Helper method that should be used by default in this class whenver
        we want to invoke Consul.kv.put()
        """
        assert key
        try:
            return self.cns.kv.put(key, data, **kwargs)
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to put value to KV') from e

    def kv_put_in_transaction(self, tx_payload: List[TxPutKV]) -> bool:
        def to_payload(v: TxPutKV) -> Dict[str, Any]:
            b64: bytes = b64encode(v.value.encode())
            b64_str = b64.decode()

            if v.cas:
                return {
                    'KV': {
                        'Key': v.key,
                        'Value': b64_str,
                        'Verb': 'cas',
                        'Index': v.cas
                    }
                }
            return {'KV': {'Key': v.key, 'Value': b64_str, 'Verb': 'set'}}

        try:
            self.cns.txn.put([to_payload(i) for i in tx_payload])
            return True
        except ClientError:
            # If a transaction fails, Consul returns HTTP 409 with the
            # JSON payload describing the reason why the transaction
            # was rejected.
            # The library transforms HTTP 409 into generic ClientException.
            # Unfortunately, we can't easily extract the payload from it.
            return False
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to put value to KV') from e

    @repeat_if_fails(max_retries=5)
    def kv_delete_in_transaction(self, tx_payload: List[KeyDelete]) -> bool:
        def to_payload(v: KeyDelete) -> Dict[str, Any]:
            return {'KV': {'Key': v.name, 'Verb':
                           'delete-tree' if v.recurse else 'delete'}}

        try:
            self.cns.txn.put([to_payload(i) for i in tx_payload])
            return True
        except ClientError:
            # If a transaction fails, Consul returns HTTP 409 with the
            # JSON payload describing the reason why the transaction
            # was rejected.
            # The library transforms HTTP 409 into generic ClientException.
            # Unfortunately, we can't easily extract the payload from it.
            return False
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(f'Failed to delete key(s)'
                                         f' from KV, error: {e}')


class CatalogAdapter:
    def __init__(self, cns: Optional[Consul] = None):
        self.cns: Consul = cns or Consul()

    def get_service_names(self) -> List[str]:
        """
        Return full list of service names currently registered in Consul
        server.
        """
        try:
            services: Dict[str, List[Any]] = self.cns.catalog.services()[1]
            return list(services.keys())
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                'Cannot access Consul catalog') from e

    def get_services(self, svc_name: str) -> List[Dict[str, Any]]:
        """
        Return service(s) registered in Consul by the given name.
        """
        try:
            # TODO refactor catalog operations into a separate class
            return self.cns.catalog.service(service=svc_name)[1]
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                'Could not access Consul Catalog') from e


class ConsulUtil:
    def __init__(self, raw_client: Optional[Consul] = None):
        self.cns: Consul = raw_client or Consul()
        self.kv = KVAdapter(cns=self.cns)
        self.catalog = CatalogAdapter(cns=self.cns)

    def _service_by_name(self, hostname: str, svc_name: str) -> Dict[str, Any]:
        cat = self.catalog
        for svc in cat.get_services(svc_name):
            if svc['Node'] == hostname:
                return svc
        raise HAConsistencyException(
            f'No {svc_name!r} Consul service found at node {hostname!r}')

    def get_local_nodename(self) -> str:
        """
        Returns the logical name of the current node. This is the name that
        Consul is aware of. In other words, whenever Consul references a node,
        it will use the names that this function can return.
        """
        try:
            local_nodename = os.environ.get('HARE_HAX_NODE_NAME') or \
                self.cns.agent.self()['Config']['NodeName']
            return local_nodename
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate '
                                         'to Consul Agent') from e

    def _local_service_by_name(self, name: str) -> Dict[str, Any]:
        """
        Returns the service data by its name assuming that it runs at the same
        node to the current hax process.
        """
        local_nodename = self.get_local_nodename()
        return self._service_by_name(local_nodename, name)

    def _service_data(self) -> ServiceData:
        my_fidk = self.get_hax_fid().key
        services = self.catalog.get_services('hax')
        for svc in services:
            if int(svc['ServiceID']) == my_fidk:
                return mkServiceData(svc)
        raise RuntimeError('Unreachable')

    def get_hax_fid(self) -> Fid:
        """
        Returns the fid of the current hax process (in other words, returns
        "my own" fid)
        """
        svc: Dict[str, Any] = self._local_service_by_name('hax')
        return mk_fid(ObjT.PROCESS, int(svc['ServiceID']))

    def get_ha_fid(self) -> Fid:
        svc = self._local_service_by_name('hax')
        return mk_fid(ObjT.SERVICE, int(svc['ServiceID']) + 1)

    def get_rm_fid(self) -> Fid:
        rm_node = self.get_session_node(self.get_leader_session())
        confd = self._service_by_name(rm_node, 'confd')
        pfidk = int(confd['ServiceID'])
        fidk = self.kv.kv_get(f'm0conf/nodes/{rm_node}/processes/{pfidk}/'
                              'services/rms')
        return mk_fid(ObjT.SERVICE, int(fidk['Value']))

    def get_hax_endpoint(self) -> str:
        return self._service_data().address

    def get_hax_ip_address(self) -> str:
        return self._service_data().ip_addr

    def fid_to_endpoint(self, proc_fid: Fid) -> Optional[str]:
        pfidk = int(proc_fid.key)
        process_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        regex = re.compile(
            f'^m0conf\\/.*\\/processes\\/{pfidk}\\/endpoint')
        for proc_item in process_items:
            match_result = re.match(regex, proc_item['Key'])
            if not match_result:
                continue
            proc_item_val = self.kv.kv_get(proc_item['Key'])
            process_ep: bytes = proc_item_val['Value']
            return process_ep.decode('utf-8')
        return None

    @repeat_if_fails()
    def get_leader_node(self) -> str:
        """
        Returns the node name of RC leader.
        Note: in case when RC leader is not elected yet, the node name may be
        just a randomly generated string (see hare-node-join script for
        more details).
        """
        leader = self.kv.kv_get('leader')
        node: bytes = leader['Value']
        return node.decode('utf-8')

    @repeat_if_fails()
    def get_leader_session(self) -> str:
        """
        Blocking version of `get_leader_session_no_wait()`.
        The method either returns the RC leader session or blocks until the
        session becomes available.
        """
        return self.get_leader_session_no_wait()

    def get_leader_session_no_wait(self) -> str:
        """
        Returns the RC leader session. HAConsistencyException is raised
        immediately if there is no RC leader selected at the moment.
        """
        leader = self.kv.kv_get('leader')
        try:
            return str(leader['Session'])
        except KeyError:
            raise HAConsistencyException(
                'Could not get the leader from Consul')

    def destroy_session(self, session: str) -> None:
        """
        Destroys the given Consul Session by name.
        The method doesn't raise any exception if the session doesn't exist.
        """
        try:
            self.cns.session.destroy(session)
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate to'
                                         ' Consul Agent: ' + str(e))

    def get_session_node(self, session_id: str) -> str:
        try:
            session = self.cns.session.info(session_id)[1]
            return str(session['Node'])  # principal RM
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate to'
                                         ' Consul Agent') from e

    def get_svc_status(self, srv_fid: Fid) -> str:
        try:
            return self.get_process_status(srv_fid).proc_status
        except Exception:
            return 'Unknown'

    def get_m0d_statuses(self) -> List[Tuple[ServiceData, ServiceHealth]]:
        """
        Return the list of all Motr service statuses according to Consul
        watchers. The following services are considered: ios, confd.
        """
        m0d_services = set(['ios', 'confd'])
        result = []
        for service_name in self.catalog.get_service_names():
            if service_name not in m0d_services:
                continue
            data = self.get_service_data_by_name(service_name)
            LOG.debug('svc data: %s', str(data))
            for item in data:
                node = self.get_process_node(item.fid)
                svc_health = self.get_service_health(node, item.fid.key)
            result += [(item, svc_health) for item in data]
        return result

    def get_service_data_by_name(self, name: str) -> List[ServiceData]:
        services = self.catalog.get_services(name)
        LOG.log(TRACE, 'Services "%s" received: %s', name, services)
        return [mkServiceData(i) for i in services]

    def get_confd_list(self) -> List[ServiceData]:
        return self.get_service_data_by_name('confd')

    def get_services_by_parent_process(self,
                                       process_fid: Fid) -> List[FidWithType]:
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        fidk = str(process_fid.key)

        # This is the RegExp to match the keys in Consul KV that describe
        # the Motr services that are enclosed into the Motr process that has
        # the given fidk.
        #
        # Note: we assume that fidk uniquely identifies the given process
        # within the whole cluster (that's why we are not interested in the
        # hostnames here).
        #
        # Examples of the key that will match:
        #   m0conf/nodes/cmu/processes/6/services/ha
        #   m0conf/nodes/cmu/processes/6/services/rms
        regex = re.compile(
            f'^m0conf\\/.*\\/processes\\/{fidk}\\/services\\/(.+)$')
        services = []
        for node in node_items:
            match_result = re.match(regex, node['Key'])
            if not match_result:
                continue
            srv_type = match_result.group(1)
            srv_fidk = int(node['Value'])
            services.append(
                FidWithType(fid=mk_fid(ObjT.SERVICE, srv_fidk),
                            service_type=srv_type))
        return services

    def get_disks_by_parent_process(self,
                                    process_fid: Fid,
                                    svc_fid: Fid) -> List[Fid]:
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        # This is the RegExp to match the keys in Consul KV that describe
        # the Motr processes and services that are enclosed into the Motr
        # process that has the given process_fid.
        #
        # Note: we assume that process_fid uniquely identifies the given
        # process within the whole cluster (that's why we are not interested
        # in the hostnames here).
        #
        # Examples of the key that will match:
        #   m0conf/nodes/0x6e00000000000001:0x3b/processes/
        #       0x7200000000000001:0x44/services/0x7300000000000001:0x46
        regex = re.compile(
            f'^m0conf\\/.*\\/processes\\/{process_fid}\\/services\\/'
            f'{svc_fid}\\/sdevs\\/([^/]+)$')
        disks = []
        for node in node_items:
            match_result = re.match(regex, node['Key'])
            if not match_result:
                continue
            sdev_fid_item = match_result.group(1)
            sdev_fidk = Fid.parse(sdev_fid_item).key
            sdev_fid = create_sdev_fid(sdev_fidk)
            disk_fid = self.sdev_to_drive_fid(sdev_fid)
            disks.append(disk_fid)
        return disks

    @repeat_if_fails()
    def is_proc_client(self, process_fid: Fid) -> bool:
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        fidk = str(process_fid.key)

        # This is the RegExp to match the keys in Consul KV that describe
        # the Motr services that are enclosed into the Motr process that has
        # the given fidk.
        # We filter out motr client entries to check if the given process fid
        # corresponds to a motr client or server process.
        #
        # Note: we assume that fidk uniquely identifies the given process
        # within the whole cluster (that's why we are not interested in the
        # hostnames here).
        #
        # Examples of the key that will match:
        #   m0conf/nodes/srvnode-1/processes/39/services/m0_client_s3
        regex = re.compile(
            f'^m0conf\\/.*\\/processes\\/{fidk}\\/services\\/(.+)$')
        for node in node_items:
            match_result = re.match(regex, node['Key'])
            if not match_result:
                continue
            srv_type = match_result.group(1)
            if 'm0_client' in srv_type:
                return True
        return False

    @repeat_if_fails()
    def get_conf_obj_status(self, obj_t: ObjT, fidk: int) -> int:

        device_obj_types: Dict[str, Callable[[ObjT, int], int]] = {
            ObjT.SDEV.name:  self.get_sdev_state,
            ObjT.DRIVE.name: self.get_sdev_state,
            ObjT.NODE.name: self.get_node_state,
            ObjT.ENCLOSURE.name: self.get_encl_state,
            ObjT.CONTROLLER.name: self.get_ctrl_state
        }
        obj_state: int = HaNoteStruct.M0_NC_ONLINE
        if obj_t.name in (ObjT.PROCESS.name, ObjT.SERVICE.name):
            # 'node/<node_name>/process/<process_fidk>/service/type'
            node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
            # TODO [KN] This code is too cryptic. To be refactored.
            keys = getattr(self,
                           'get_{}_keys'.format(
                                obj_t.name.lower()))(node_items, fidk)
            assert len(keys) == 1
            key = keys[0].split('/')
            node_key = ('/'.join(key[:3]))
            node_val = self.kv.kv_get(node_key)
            data = node_val['Value']
            node_name: str = json.loads(data)['name']
            if (self.get_node_health(node_name) != 'passing'):
                obj_state = HaNoteStruct.M0_NC_FAILED

        if obj_t.name in (ObjT.PROCESS.name, ObjT.SERVICE.name):
            obj_state = self.get_proc_svc_conf_obj_status(obj_t, fidk)

        elif obj_t.name in device_obj_types:
            obj_state = device_obj_types[obj_t.name](obj_t, fidk)

        return obj_state

    def get_proc_svc_conf_obj_status(self, obj_t: ObjT, fidk: int) -> int:
        if ObjT.SERVICE.name == obj_t.name:
            svc_fid = create_service_fid(fidk)
            pfid = self.get_service_process_fid(svc_fid)
        else:
            pfid = create_process_fid(fidk)
        proc_node = self.get_process_node(pfid)
        if (self.get_service_health(proc_node, fidk) in
                (ServiceHealth.OK, ServiceHealth.UNKNOWN)):
            return HaNoteStruct.M0_NC_ONLINE
        else:
            return HaNoteStruct.M0_NC_FAILED

    @staticmethod
    def get_process_keys(node_items: List[Any], fidk: int) -> List[Any]:
        fid = mk_fid(ObjT.PROCESS, fidk)
        return [
            x['Key'] for x in node_items
            if f'{fid}' == x['Key'].split('/')[-1]
        ]

    @staticmethod
    def get_service_keys(node_items: List[Any], fidk: int) -> List[Any]:
        fid = mk_fid(ObjT.SERVICE, fidk)
        return [
            x['Key'] for x in node_items
            if f'{fid}' == x['Key'].split('/')[-1]
        ]

    def is_node_alive(self, node: str) -> bool:
        """
        Checks via Consul Members API whether the given node is alive.
        """
        try:
            # Returns data of the following kind:
            # [{
            #     'Name': 'localhost',
            #     'Addr': '192.168.6.214',
            #     'Port': 8301,
            #     'Tags': {
            #         'acls': '0',
            #         'bootstrap': '1',
            #         'build': '1.7.8:9a5a1218',
            #         'dc': 'dc1',
            #         'id': 'dd8a91f6-ca32-30e0-983c-8f309d653045',
            #         'port': '8300',
            #         'raft_vsn': '3',
            #         'role': 'consul',
            #         'segment': '',
            #         'vsn': '2',
            #         'vsn_max': '3',
            #         'vsn_min': '2',
            #         'wan_join_port': '8302'
            #     },
            #     'Status': 1,
            #     'ProtocolMin': 1,
            #     'ProtocolMax': 5,
            #     'ProtocolCur': 2,
            #     'DelegateMin': 2,
            #     'DelegateMax': 5,
            #     'DelegateCur': 4
            # }]
            members_data = self.cns.agent.members()
            LOG.log(TRACE, "members: %s", members_data)
            for member in members_data:
                if member['Name'] == node:
                    return int(member['Status']) == 1
            return True
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                'Failed to members data from Consul') from e

    def get_node_health(self, node: str) -> str:
        try:
            node_data = self.cns.health.node(node)[1]
            if not node_data or (not self.is_node_alive(node)):
                return 'failed'
            return str(node_data[0]['Status'])
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                f'Failed to get {node} node health') from e

    @repeat_if_fails()
    def get_node_fid(self, node: str) -> Optional[Fid]:
        """
        Returns the fid of the given node.

        Parameters:
            node : hostname of the node.
        """
        # Example,
        # m0conf/nodes/
        # 0x6e00000000000001:0x3:{"name": "ssc-vm-1623.colo.seagate.com",
        #                         "state": "M0_NC_UNKNOWN"}
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        for item in node_items:
            key = item['Key']
            key_split = key.split('/')
            if len(key_split) != 3:
                # Although we make a recurse scan, we don't need anything
                # deeper than 1 level down (see Example above).
                continue
            item_value = json.loads(item['Value'])
            if 'name' in item_value and item_value['name'] == node:
                node_fid: str = str(key_split[2])
                return Fid.parse(node_fid)
        return None

    @repeat_if_fails()
    def get_node_name_by_fid(self, node_fid: Fid) -> Optional[str]:
        """
        Returns the node name by its FID value or None if the given FID doesn't
        correspond to any node.
        """
        node_data = self.kv.kv_get(f'm0conf/nodes/{node_fid}')
        if node_data:
            parsed = json.loads(node_data['Value'])
            name: str = parsed['name']
            return name
        return None

    @repeat_if_fails()
    def get_node_ctrl_fids(self, node: str) -> Optional[List[Fid]]:
        """
        Parameters:
            node : hostname of the node.
        """
        # Example,
        # [
        #    "key": "m0conf/sites/0x5300000000000001:0x1/
        #            racks/0x6100000000000001:0x2/encls/
        #            0x6500000000000001:0x4/ctrls/0x6300000000000001:0x5",
        # ]
        encl_fid = self.get_node_encl_fid(node)
        if not encl_fid:
            return None
        ctrl_items = self.get_all_sites()
        regex = re.compile(
            f'^m0conf\\/.*\\/racks\\/.*\\/encls\\/{encl_fid}\\/ctrls\\/'
            '([^/]+)$')
        list_fids: List[Fid] = []
        for ctrl in ctrl_items:
            match_result = re.match(regex, ctrl['Key'])
            if not match_result:
                continue
            ctrl_fid: str = match_result.group(1)
            list_fids.append(Fid.parse(ctrl_fid))
        return list_fids

    @repeat_if_fails()
    def get_io_service_devices(self,
                               ioservice_fid: Fid) -> Optional[List[str]]:
        if not ioservice_fid:
            return None
        # Example key m0conf/nodes/0x6e00000000000001:0x3/processes/
        #   0x7200000000000001:0x15/services/0x7300000000000001:0x17/sdevs/
        #   0x6400000000000001:0x18:{"path": "/dev/sdc", "state": "offline"}
        sdev_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        regex = re.compile(
            f'^m0conf\\/.*\\/processes\\/{ioservice_fid}\\/.*\\/sdevs\\/.*$')
        sdev_fids = []
        for sdev in sdev_items:
            match_result = re.match(regex, sdev['Key'])
            if not match_result:
                continue
            sdev_key: str = match_result.group(0)
            key = sdev_key.split('/')
            sdev_fids.append(key[8])
        return sdev_fids

    @repeat_if_fails()
    def get_all_sites(self):
        return self.kv.kv_get('m0conf/sites', recurse=True)

    @repeat_if_fails()
    def get_device_controller(self, sdev_fid):
        # Example key m0conf/sites/0x5300000000000001:0x1/racks/
        #    0x6100000000000001:0x2/encls/0x6500000000000001:0x4/ctrls/
        #    0x6300000000000001:0x5/drives/0x6b00000000000001:0x38:
        #    {"sdev": "0x6400000000000001:0x37", "state": "M0_NC_UNKNOWN"}
        sites_items = self.get_all_sites()

        for item in sites_items:
            if 'sdev' not in json.loads(item['Value']).keys():
                continue

            if json.loads(item['Value'])['sdev'] == f'{sdev_fid}':
                key = item['Key'].split('/')
                return key[8]

        return None

    @repeat_if_fails()
    def get_ioservice_ctrl_fid(self, ioservice_fid: Fid) -> Optional[Fid]:
        """
        Returns the fid of the controller for the given IOservice.

        Parameters:
            ioservice_fid : Fid of IO service for which ctrl fid is required.

        TODO: Instead of comparing devices, add a mapping from controller
              to I/O service
        """
        if not ioservice_fid:
            return None

        sdev_fids = self.get_io_service_devices(ioservice_fid)

        if not sdev_fids:
            return None

        sdev_fid = sdev_fids[0]

        ctrl_fid = self.get_device_controller(sdev_fid)

        if ctrl_fid is None:
            return None
        else:
            return Fid.parse(ctrl_fid)

    @repeat_if_fails()
    def all_io_services_failed(self, node: str) -> bool:
        """
        Checks if all the IO services of given node are in failed state.

        Parameters:
            node : hostname of the node.
        """
        node_fid = self.get_node_fid(node)

        # Example m0conf/nodes/0x6e00000000000001:0x3/processes/
        # 0x7200000000000001:0xa/services/0x7300000000000001:0xc:
        # {"name": "ios", "state": "M0_NC_UNKNOWN"}

        sites_items = self.kv.kv_get(f'm0conf/nodes/{node_fid}/processes',
                                     recurse=True)
        for item in sites_items:
            if 'name' not in json.loads(item['Value']).keys():
                continue

            if json.loads(item['Value'])['name'] == 'ios':
                # m0conf/nodes/0x6e00000000000001:0x3/processes/
                # 0x7200000000000001:0xa:
                # {"name": "m0_server", "state": "online"}
                p_fid = item['Key'].split('/')[4]
                p_key = f"m0conf/nodes/{node_fid}/processes/{p_fid}"
                process = self.kv.kv_get(p_key, recurse=False)
                if not process:
                    raise HAConsistencyException('Failed to get process key')

                state = json.loads(process['Value'])['state']
                if state not in ('stopped', 'failed', 'offline'):
                    return False

        return True

    @repeat_if_fails()
    def get_node_encl_fid(self, node: str) -> Optional[Fid]:
        """
        Returns the fid of the enclosure for the given node.

        Parameters:
            node : hostname of the node.
        """
        # Example,
        # {
        #    "key": "m0conf/sites/0x5300000000000001:0x1/
        #            racks/0x6100000000000001:0x2/encls/
        #            0x6500000000000001:0x4",
        #    "value": "{\"node\": \"0x6e00000000000001:0x3\",
        #               \"state\": \"M0_NC_UNKNOWN\"}"
        # },
        node_fid = self.get_node_fid(node)
        if not node_fid:
            return None
        encl_items = self.kv.kv_get('m0conf/sites', recurse=True)
        regex = re.compile(
            '^m0conf\\/.*\\/racks\\/.*\\/encls\\/([^/]+)$')
        for encl in encl_items:
            match_result = re.match(regex, encl['Key'])
            if not match_result:
                continue
            encl_value = json.loads(encl['Value'])
            if 'node' in encl_value and encl_value['node'] == str(node_fid):
                encl_fid: str = match_result.group(1)
                return Fid.parse(encl_fid)
        return None

    def get_device_ha_state(self, status: ServiceHealth) -> str:

        device_ha_state_map = {
            ServiceHealth.UNKNOWN: m0HaObjState.M0_NC_UNKNOWN,
            ServiceHealth.OK: m0HaObjState.M0_NC_ONLINE,
            ServiceHealth.OFFLINE: m0HaObjState.M0_NC_TRANSIENT,
            ServiceHealth.FAILED: m0HaObjState.M0_NC_FAILED}
        return device_ha_state_map[status].name

    @repeat_if_fails()
    def set_node_state(self, node_fid: Fid, status: ServiceHealth) -> None:
        # Example,
        # {
        #    "key": "m0conf/nodes/0x6e00000000000001:0x3",
        #    "value": "{\"name\": \"srvnode-1.data.private\",
        #               \"state\": \"M0_NC_UNKNOWN\"}"
        # }
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        regex = re.compile(
            f'^m0conf/nodes/{node_fid}$')
        for node in node_items:
            match_result = re.match(regex, node['Key'])
            if not match_result:
                continue
            value = json.loads(node['Value'])
            value['state'] = self.get_device_ha_state(status)
            LOG.debug('Setting node=%s in KV with state=%s',
                      node_fid, value['state'])
            self.kv.kv_put(node['Key'], json.dumps(value))

    @repeat_if_fails()
    def set_encl_state(self, encl_fid: Fid, status: ServiceHealth) -> None:
        # Example,
        # {
        #    "key": "m0conf/sites/0x5300000000000001:0x1/
        #            racks/0x6100000000000001:0x2/encls/
        #            0x6500000000000001:0x4",
        #    "value": "{\"node\": \"0x6e00000000000001:0x3\",
        #               \"state\": \"M0_NC_UNKNOWN\"}"
        # }
        node_items = self.get_all_sites()
        regex = re.compile(
            f'^m0conf\\/.*\\/{encl_fid}$')
        for encl in node_items:
            match_result = re.match(regex, encl['Key'])
            if not match_result:
                continue
            value = json.loads(encl['Value'])
            value['state'] = self.get_device_ha_state(status)
            LOG.debug('Setting enclosure=%s in KV with state=%s',
                      encl_fid, value['state'])
            self.kv.kv_put(encl['Key'], json.dumps(value))

    @repeat_if_fails()
    def set_ctrl_state(self, ctrl_fid: Fid, status: ServiceHealth) -> None:
        # Example,
        # {
        #    "key": "m0conf/sites/0x5300000000000001:0x1/
        #            racks/0x6100000000000001:0x2/encls/
        #            0x6500000000000001:0x4/ctrls/
        #            0x6300000000000001:0x5",
        #    "value": "{\"state\": \"M0_NC_UNKNOWN\"}"
        # }
        ctrl_items = self.get_all_sites()
        regex = re.compile(f'^m0conf\\/.*\\/ctrls/{ctrl_fid}$')
        for ctrl in ctrl_items:
            match_result = re.match(regex, ctrl['Key'])
            if not match_result:
                continue
            value = json.loads(ctrl['Value'])
            value['state'] = self.get_device_ha_state(status)
            LOG.debug('Setting ctrl=%s in KV with state=%s',
                      ctrl_fid, value['state'])
            self.kv.kv_put(ctrl['Key'], json.dumps(value))

    @repeat_if_fails()
    def get_ctrl_state(self, obj_t: ObjT, fidk: int) -> int:
        assert obj_t.value == ObjT.CONTROLLER.value
        ctrl_fid = mk_fid(ObjT.CONTROLLER, fidk)
        ctrl_items = self.get_all_sites()
        regex = re.compile(f'^m0conf\\/.*\\/ctrls/{ctrl_fid}$')
        for ctrl in ctrl_items:
            match_result = re.match(regex, ctrl['Key'])
            if not match_result:
                continue
            val = json.loads(ctrl['Value'])
            state = val['state']
            LOG.debug('Controller=%s state=%s', ctrl_fid, state)
            if state in (m0HaObjState.M0_NC_ONLINE.name,
                         m0HaObjState.M0_NC_TRANSIENT.name,
                         m0HaObjState.M0_NC_FAILED.name):
                return m0HaObjState.parse(state)
        return m0HaObjState.M0_NC_ONLINE

    @repeat_if_fails()
    def get_encl_state(self, obj_t: ObjT, fidk: int) -> int:
        assert obj_t.value == ObjT.ENCLOSURE.value
        encl_fid = mk_fid(ObjT.ENCLOSURE, fidk)
        encl_items = self.get_all_sites()
        regex = re.compile(f'^m0conf\\/.*\\/encls/{encl_fid}$')

        for encl in encl_items:
            match_result = re.match(regex, encl['Key'])
            if not match_result:
                continue
            val = json.loads(encl['Value'])
            state = val['state']
            LOG.debug('Enclosure=%s state=%s', encl_fid, state)
            if state in (m0HaObjState.M0_NC_ONLINE.name,
                         m0HaObjState.M0_NC_TRANSIENT.name,
                         m0HaObjState.M0_NC_FAILED.name):
                return m0HaObjState.parse(state)
        return m0HaObjState.M0_NC_ONLINE

    @repeat_if_fails()
    def get_node_state(self, obj_t: ObjT, fidk: int) -> int:
        assert obj_t.value == ObjT.NODE.value
        node_fid = mk_fid(ObjT.NODE, fidk)
        node = self.kv.kv_get(f'm0conf/nodes/{node_fid}', recurse=False)
        if node:
            val = json.loads(node['Value'])
            state = val['state']
            LOG.debug('Node=%s state=%s', node_fid, state)
            if state in (m0HaObjState.M0_NC_ONLINE.name,
                         m0HaObjState.M0_NC_TRANSIENT.name,
                         m0HaObjState.M0_NC_FAILED.name):
                return m0HaObjState.parse(state)
        return m0HaObjState.M0_NC_ONLINE

    @staticmethod
    def _to_canonical_service_data(service: Dict[str, Any]) -> ServiceData:
        node = service['Node']
        fidk = int(service['ServiceID'])
        srv_ip_addr = service['Address']
        srv_address = service['ServiceAddress']
        srv_port = service['ServicePort']
        return ServiceData(node=node,
                           fid=create_process_fid(fidk),
                           ip_addr=srv_ip_addr,
                           address=f'{srv_address}:{srv_port}')

    def update_fs_stats(self, stats_data: FsStatsWithTime) -> None:
        # TODO investigate whether we can replace json with simplejson in
        # all the cases
        data_str = simplejson.dumps(stats_data)
        self.kv.kv_put('stats/filesystem', data_str)

    @repeat_if_fails()
    def update_process_status(self, event: ConfHaProcess) -> None:
        assert 0 <= event.chp_event < len(ha_process_events), \
            f'Invalid event type: {event.chp_event}'
        local_node = self.get_local_nodename()
        data = json.dumps({'state': ha_process_events[event.chp_event],
                           'type': m0HaProcessType(event.chp_type).name})
        # Maintain statuses for all the motr processes in the cluster
        # for every node so that in case of 1 or more node failures,
        # as every node will receive the node failure event, the failed
        # processes statuses will be updated locally without each node
        # stepping over each other's update and without any need for
        # synchronization.
        key = f'{local_node}/processes/{event.fid}'
        LOG.debug('Setting process status in KV: %s:%s', key, data)
        self.kv.kv_put(key, data)

    def update_drive_state(self,
                           drive_fids: List[Fid],
                           status: ServiceHealth,
                           device_event=True) -> None:
        device_state_map = {
            ServiceHealth.OK: 'online',
            ServiceHealth.FAILED: 'failed',
            ServiceHealth.OFFLINE: 'offline',
        }
        for drive in drive_fids:
            sdev_fid = self.drive_to_sdev_fid(drive)
            self.set_sdev_state(sdev_fid, device_state_map[status],
                                device_event)

    @repeat_if_fails()
    def set_sdev_state(self,
                       sdev_fid: Fid,
                       state: str,
                       device_event=True) -> None:
        LOG.debug('Setting sdev=%s in KV with state=%s', sdev_fid, state)
        sdev_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        regex = re.compile(
            f'^m0conf\\/.*\\/sdevs\\/{sdev_fid}$')
        for sdev in sdev_items:
            match_result = re.match(regex, sdev['Key'])
            if not match_result:
                continue
            value = json.loads(sdev['Value'])
            if not device_event and value['state'] == 'failed':
                continue
            value['state'] = state
            self.kv.kv_put(sdev['Key'], json.dumps(value))

    @repeat_if_fails()
    def get_sdev_state(self, obj_t: ObjT, fidk: int) -> int:
        drive_to_ha_state_map = {
            'unknown': HaNoteStruct.M0_NC_UNKNOWN,
            'online': HaNoteStruct.M0_NC_ONLINE,
            'offline': HaNoteStruct.M0_NC_TRANSIENT,
            'failed': HaNoteStruct.M0_NC_FAILED}
        if obj_t.name == ObjT.DRIVE.name:
            drive_fid = create_drive_fid(fidk)
            sdev_fid = self.drive_to_sdev_fid(drive_fid)
        else:
            sdev_fid = create_sdev_fid(fidk)
        sdev_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        regex = re.compile(
            f'^m0conf\\/.*\\/sdevs\\/{sdev_fid}$')
        for sdev in sdev_items:
            match_result = re.match(regex, sdev['Key'])
            if not match_result:
                continue
            val = json.loads(sdev['Value'])
            LOG.debug('Sdev=%s state=%s', str(sdev_fid), val['state'])
            if str(val['state']).lower() in ('unknown', 'offline', 'failed'):
                return drive_to_ha_state_map[str(val['state']).lower()]

        return HaNoteStruct.M0_NC_ONLINE

    @repeat_if_fails()
    def drive_to_sdev_fid(self, drive_fid: Fid) -> Fid:
        # We extract the sdev fid as follows,
        # e.g. drive_fid=0x6400000000000001:0x2d
        # 1. m0conf/sites/0x5300000000000001:0x1/racks/0x6100000000000001:0x2/
        #    encls/0x6500000000000001:0x21/ctrls/0x6300000000000001:0x22/
        #    drives/0x6b00000000000001:0x2d:{"sdev": "0x6400000000000001:0x2c",
        #    "state": "M0_NC_UNKNOWN"}
        # 2. Fetch Consul kv for sdev fid
        # 3. Extract sdev fid key from the sdev fid.
        # 4. Create sdev fid from fid key.
        sdev_fid: Fid = Fid(0, 0)
        sdev_items = self.kv.kv_get('m0conf/sites', recurse=True)
        regex = re.compile(
            f'^m0conf\\/.*\\/drives/{drive_fid}$')
        for x in sdev_items:
            match_result = re.match(regex, x['Key'])
            if not match_result:
                continue
            sdev_fid_item = json.loads(x['Value'])['sdev']
            sdev_fidk = Fid.parse(sdev_fid_item).key
            sdev_fid = create_sdev_fid(sdev_fidk)
            break
        return sdev_fid

    @repeat_if_fails()
    def sdev_to_drive_fid(self, sdev_fid: Fid):
        # We extract the drive fid as follows,
        # e.g. sdev_fid=0x6400000000000001:0x2c
        # 1. m0conf/sites/0x5300000000000001:0x1/racks/0x6100000000000001:0x2/
        #    encls/0x6500000000000001:0x21/ctrls/0x6300000000000001:0x22/
        #    drives/0x6b00000000000001:0x2d:{"sdev": "0x6400000000000001:0x2c",
        #    "state": "M0_NC_UNKNOWN"}
        # 2. Fetch Consul kv for drive fid
        # 3. Extract drive fid key from the drive fid.
        # 4. Create drive fid from fid key.
        drive_fid: Fid = Fid(0, 0)
        drive_items = self.kv.kv_get('m0conf/sites', recurse=True)
        for x in drive_items:
            if '/drives/' in x['Key']:
                if json.loads(x['Value'])['sdev'] == f'{sdev_fid}':
                    # Using constant index 10 for the drive fid.
                    # Fix this by changing the Consul schema to have
                    # mapping of sdev fid to drive fid direct mapping.
                    drive_fid_item = x['Key'].split('/')[10]
                    drive_fidk = Fid.parse(drive_fid_item).key
                    drive_fid = create_drive_fid(drive_fidk)
                    break
        return drive_fid

    @repeat_if_fails()
    def node_to_drive_fid(self, node_name: str, drive: str):
        sdev_fid: Fid = Fid(0, 0)
        # We extract the sdev fid as follows,
        # e.g. node_name=ssc-vm-c-0553.colo.seagate.com
        #      drive=/dev/vdf
        # 1. m0conf/nodes/ssc-vm-c-0553.colo.seagate.com/processes/41/
        #     services/ios:43
        # 2. Create ioservice motr fid
        # 3. fetch consul kv for ios fid,
        #    m0conf/nodes/0x6e00000000000001:0x20/processes/
        #    0x7200000000000001:0x29/services/0x7300000000000001:0x2b/
        #    sdevs/0x6400000000000001:0x2c:
        #    {"path": "/dev/vdf", "state": "M0_NC_UNKNOWN"}
        # 4. find drive name in the json value and extract sdev fid from the
        #    key 0x6400000000000001:0x2c
        # 5. Create sdev fid from sdev fid key.
        process_items = self.kv.kv_get(f'm0conf/nodes/{node_name}/processes',
                                       recurse=True)
        for x in process_items:
            if '/ios' in x['Key']:
                fidk_ios = x['Value']
        ios_fid = create_service_fid(int(fidk_ios))
        sdev_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        for x in sdev_items:
            if f'/{ios_fid}/' in x['Key']:
                if json.loads(x['Value'])['path'] == drive:
                    # Using constant index 8 for the sdev fid.
                    # Fix this by changing the Consul schema to have
                    # mapping of drive path to sdev direct mapping.
                    sdev_fid_item = x['Key'].split('/')[8]
                    sdev_fidk = Fid.parse(sdev_fid_item).key
                    sdev_fid = create_sdev_fid(sdev_fidk)
                    break
        return self.sdev_to_drive_fid(sdev_fid)

    # Returns status of process from its local node.
    def get_process_status(self, fid: Fid) -> MotrConsulProcInfo:
        proc_node = self.get_process_node(fid)
        key = f'{proc_node}/processes/{fid}'
        status = self.kv.kv_get(key)
        if status:
            val = json.loads(status['Value'])
            return MotrConsulProcInfo(val['state'], val['type'])
        else:
            return MotrConsulProcInfo('Unknown', 'Unknown')

    def get_process_local_status(self, fid: Fid) -> str:
        local_node = self.get_local_nodename()
        key = f'{local_node}/processes/{fid}'
        status = self.kv.kv_get(key)
        if status:
            return str(json.loads(status['Value'])['state'])
        else:
            return 'Unknown'

    def drive_name_to_id(self, uid: str) -> str:
        drive_id = ''
        # 'm0conf/nodes/<node_name>/processes/<process_fidk>/disks/<disk_uuid>'
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        for x in node_items:
            if '/disks/' in x['Key'] and uid in x['Key']:
                drive_id = x['Value']
        return drive_id

    def set_m0_disk_state(self, fid: str, objstate: int) -> None:
        assert 0 <= objstate < len(ha_conf_obj_states), \
            f'Invalid object state: {objstate}'

        data = json.dumps({'state': ha_conf_obj_states[objstate]})
        key = f'process/{fid}'
        LOG.debug('Setting disk state in KV: %s:%s', key, data)
        self.kv.kv_put(key, data)

    # It is tricky to report a correct service status due to various
    # failure conditions. Consul notification can be delayed, the
    # corresponding process might be already restarting. Thus, following
    # algorithm is used,
    # 1. Consul watcher for the services notifies 'passing' if the
    #    corresponding systemd status is active or activating.
    # 2. If systemd status for a motr process is 'deactivating' or 'inactive',
    #    corresponding consul watcher notifies 'warning'.
    # 3. If systemd status for the motr process is 'failed', corresponding
    #    Consul watcher notifies 'failed'
    # 4. Based on the Consul notification, we also check node status, if
    #    node status is not 'passing', function returns ServiceHealth.FAILED.
    # 5. If node status is 'passing' or 'warning', function checks the motr
    #    status in Consul KV and reports as follows,
    #    Service status      Consul KV                   result
    #    passing         'M0_CONF_HA_PROCESS_STARTING'  OFFLINE(no-op)
    #    passing         'M0_CONF_HA_PROCESS_STOPPING'  OFFLINE(no-op)
    #    passing         'M0_CONF_HA_PROCESS_STARTED'   OK(ONLINE)
    #    passing         'M0_CONF_HA_PROCESS_STOPPED'   UNKNOWN(Not sure)
    #    warning         'M0_CONF_HA_PROCESS_STOPPING'  FAILED(iff remote node)
    #    warning         'M0_CONF_HA_PROCESS_STARTED'   OFFLINE(iff local node)
    #    failed          N/A                            FAILED
    # Addition to this, hax maintains processes statuses of the entire cluster
    # for every node. This avoid synchronisation issues and over writing each
    # other's statuses.
    @repeat_if_fails()
    def get_service_health(self, node: str, svc_id: int) -> ServiceHealth:
        """
        Returns current status of a Consul service identified by the given
        svc_id for a given node.
        """
        # Maps consul service status and motr process status to the
        # corresponding ha status to be notified.
        # Respective values are for local and remote nodes.
        # {(consul_svc_status, motr_process_status):(local_node_ha_status,
        #                                            remote_node_ha_status)}

        cur_consul_status = MotrConsulProcStatus
        local_remote_health_ret = MotrProcStatusLocalRemote

        svc_to_motr_status_map = {
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STARTING'):
            local_remote_health_ret(ServiceHealth.OFFLINE,
                                    ServiceHealth.OK),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STOPPING'):
            local_remote_health_ret(ServiceHealth.OFFLINE,
                                    ServiceHealth.UNKNOWN),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STARTED'):
            local_remote_health_ret(ServiceHealth.OK,
                                    ServiceHealth.OK),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STOPPED'):
            local_remote_health_ret(ServiceHealth.OFFLINE,
                                    ServiceHealth.UNKNOWN),
            cur_consul_status('passing', 'Unknown'):
            local_remote_health_ret(ServiceHealth.UNKNOWN,
                                    ServiceHealth.UNKNOWN),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STOPPING'):
            local_remote_health_ret(ServiceHealth.OFFLINE,
                                    ServiceHealth.STOPPED),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STARTED'):
            local_remote_health_ret(ServiceHealth.OFFLINE,
                                    ServiceHealth.FAILED),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STOPPED'):
            local_remote_health_ret(ServiceHealth.STOPPED,
                                    ServiceHealth.STOPPED),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STARTING'):
            local_remote_health_ret(ServiceHealth.OFFLINE,
                                    ServiceHealth.OFFLINE),
            cur_consul_status('warning', 'Unknown'):
            local_remote_health_ret(ServiceHealth.UNKNOWN,
                                    ServiceHealth.UNKNOWN)}
        try:
            node_data: List[Dict[str, Any]] = self.cns.health.node(node)[1]
            if not node_data:
                return ServiceHealth.FAILED
            node_status = str(node_data[0]['Status'])
            if node_status != 'passing' or (not self.is_node_alive(node)):
                return ServiceHealth.FAILED
            status = ServiceHealth.UNKNOWN
            for item in node_data:
                if item['ServiceID'] == str(svc_id):
                    LOG.debug('item.status %s', item['Status'])
                    if item['Status'] == 'critical':
                        return ServiceHealth.FAILED
                    pfid = create_process_fid(svc_id)
                    cns_status = self.get_process_status(pfid)
                    svc_health = svc_to_motr_status_map[MotrConsulProcStatus(
                                         item['Status'],
                                         cns_status.proc_status)]
                    LOG.debug('consul.status %s svc_health: %s',
                              cns_status, svc_health)
                    local_node = self.get_local_nodename()
                    proc_node = self.get_process_node(pfid)
                    if proc_node == local_node:
                        status = svc_health.motr_proc_status_local
                    else:
                        status = svc_health.motr_proc_status_remote
                    if (status == ServiceHealth.FAILED and
                            cns_status.proc_type == (
                            m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS.name)):
                        status = ServiceHealth.STOPPED

                    # This situation is not expected but we handle
                    # the same. Hax may end up here if the process has stopped
                    # already and its current status is also reported as
                    # 'unknown' by Consul. Hax will do nothing in this case
                    # and will report OFFLINE for that process.
                    if (item['Status'] == 'warning' and
                            cns_status.proc_status == 'Unknown' and
                            status == ServiceHealth.UNKNOWN):
                        status = ServiceHealth.OFFLINE

                    return status
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate '
                                         'to Consul Agent') from e
        return status

    def get_process_node(self, proc_fid: Fid) -> str:
        fidk = proc_fid.key
        # 'node/<node_name>/process/<process_fidk>/service/type'
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        if ObjT.PROCESS.value == proc_fid.container:
            keys = self.get_process_keys(node_items, fidk)
        elif ObjT.SERVICE.value == proc_fid.container:
            keys = self.get_service_keys(node_items, fidk)

        assert len(keys) == 1
        key = keys[0].split('/')
        node_key = ('/'.join(key[:3]))
        node_val = self.kv.kv_get(node_key)
        data = node_val['Value']
        return str(json.loads(data)['name'])

    def get_service_process_fid(self, svc_fid: Fid) -> Fid:
        assert ObjT.SERVICE.value == svc_fid.container
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        keys = self.get_service_keys(node_items, svc_fid.key)
        assert len(keys) == 1
        process_fid: str = keys[0].split('/')[4]
        pfid = Fid.parse(process_fid)
        return pfid

    def get_profiles(self) -> List[Profile]:
        def to_profile(k: str, v: Dict[str, Any]) -> Profile:
            return Profile(fid=Fid.parse(k),
                           name=v['name'],
                           pool_names=v['pools'])

        result: List[Profile] = []
        for x in self.kv.kv_get('m0conf/profiles/', recurse=True):
            fidstr = x['Key'].split('/')[-1]
            payload = simplejson.loads(x['Value'])
            result.append(to_profile(fidstr, payload))
        return result

    @repeat_if_fails()
    def ensure_ioservices_running(self) -> List[bool]:
        statuses = self.get_m0d_statuses()
        LOG.debug('The following statuses received: %s', statuses)
        # started = ['M0_CONF_HA_PROCESS_STARTED' == v[1] for v in statuses]
        started = [ServiceHealth.OK == v[1] for v in statuses]
        return started

    @repeat_if_fails()
    def ensure_motr_all_started(self, event: Event):
        while True:
            started = self.ensure_ioservices_running()
            if all(started):
                LOG.debug('According to Consul all confds have been started')
                return
            wait_for_event(event, 2)

    def m0ds_stopping(self) -> bool:
        # statuses = self.get_m0d_statuses()
        statuses = self.get_m0d_statuses()
        LOG.debug('The following statuses received: %s', statuses)
        # stopping = [v[1] in ('M0_CONF_HA_PROCESS_STOPPING',
        #                      'M0_CONF_HA_PROCESS_STOPPED') for v in statuses]
        stopping = [v[1] in (ServiceHealth.OFFLINE,
                             ServiceHealth.STOPPED) for v in statuses]
        return all(stopping)

    def get_process_current_status(self, status_reported: ServiceHealth,
                                   proc_fid: Fid) -> ServiceHealth:
        status_current = status_reported
        # Reconfirm the process status only if the reported status is FAILED.
        node = self.get_process_node(proc_fid)
        status_current = self.get_service_health(node,
                                                 proc_fid.key)
        LOG.info('node: %s proc: %s current status: %s',
                 node, proc_fid, status_current)
        return status_current

    def svcHealthToM0Status(self, svc_health: ServiceHealth):
        svcHealthToM0status: dict = {
            ServiceHealth.OK: m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED,
            ServiceHealth.FAILED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ServiceHealth.UNKNOWN: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ServiceHealth.STOPPED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED
        }
        return svcHealthToM0status[svc_health]

    def service_health_to_m0dstatus_update(self, proc_fid: Fid,
                                           svc_health: ServiceHealth):
        ev = ConfHaProcess(chp_event=self.svcHealthToM0Status(svc_health),
                           chp_type=int(
                                m0HaProcessType.M0_CONF_HA_PROCESS_M0D),
                           chp_pid=0,
                           fid=proc_fid)
        self.update_process_status(ev)

    def is_confd_failed(self, proc_fid: Fid) -> bool:
        status = self.get_process_status(proc_fid).proc_status
        return status in ('M0_CONF_HA_PROCESS_STOPPING',
                          'M0_CONF_HA_PROCESS_STOPPED',
                          'M0_CONF_HA_PROCESS_STARTING')

    @repeat_if_fails()
    def set_process_state(self,
                          process_fid: Fid,
                          state: ServiceHealth) -> None:
        LOG.debug('Setting process=%s in KV with state=%s',
                  process_fid, state)
        process_state_map = {
            ServiceHealth.OK: 'online',
            ServiceHealth.FAILED: 'failed',
            ServiceHealth.OFFLINE: 'offline',
            ServiceHealth.UNKNOWN: 'unknown',
            ServiceHealth.STOPPED: 'stopped',
        }

        # Example key is as follows
        # m0conf/nodes/0x6e00000000000001:0x3/processes/0x7200000000000001:
        # 0x15:{"name": "m0_server", "state": "M0_NC_UNKNOWN"}
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        regex = re.compile(
            f'^m0conf\\/nodes\\/.*\\/processes\\/{process_fid}$')
        for item in node_items:
            match_result = re.match(regex, item['Key'])
            if not match_result:
                continue
#            value = item['Value']
            value = json.loads(item['Value'])
            value['state'] = process_state_map[state]
            self.kv.kv_put(item['Key'], json.dumps(value))


def dump_json(obj) -> str:
    """
    Interface wrapper to automatically apply correct parameters for json
    serialization obj.
    """
    return simplejson.dumps(obj, for_json=True)
