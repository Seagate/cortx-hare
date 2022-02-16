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

import inject
import json
import logging
import os
import re
from base64 import b64encode
from functools import wraps
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from hax.log import TRACE
from threading import Event, Lock
from time import sleep

import simplejson
from consul import Consul, ConsulException
from consul.base import ClientError
from requests.exceptions import RequestException
from urllib3.exceptions import HTTPError

from hax.common import HaxGlobalState
from hax.exception import HAConsistencyException, InterruptedException
from hax.types import (ByteCountStats, ConfHaProcess, Fid, FsStatsWithTime,
                       ObjT, ObjHealth, ObjTMaskMap, Profile, PverInfo, PverState,
                       m0HaProcessEvent, m0HaProcessType, KeyDelete,
                       HaNoteStruct, m0HaObjState)

from hax.consul.cache import (uses_consul_cache, invalidates_consul_cache,
                              supports_consul_cache)

__all__ = ['ConsulUtil', 'create_process_fid', 'create_service_fid',
           'create_sdev_fid', 'create_drive_fid']

LOG = logging.getLogger('hax')

motr_processes_status: dict = {}

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
                                'motr_proc_status_local', ObjHealth),
                                ('motr_proc_status_remote', ObjHealth)])

ObjStatus = NamedTuple("ObjStatus", [("resource_type", ObjT), ("status", str)])


def consul_to_local_nodename(consul_node: str) -> str:
    return consul_node.split(':')[0]


def mkServiceData(service: Dict[str, Any]) -> ServiceData:
    transport_type = service['ServiceMeta']['transport_type']
    if transport_type == 'lnet':
        addr = '{}:{}'.format(service['ServiceAddress'],
                              service['ServicePort'])
    else:
        addr = '{}@{}'.format(service['ServiceAddress'],
                              service['ServicePort'])
    return ServiceData(
        node=consul_to_local_nodename(service['Node']),
        fid=mk_fid(
            ObjT.PROCESS,  # XXX s/PROCESS/SERVICE/ ?
            int(service['ServiceID'])),
        ip_addr=service['Address'],
        address=addr)


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
                     'M0_CONF_HA_PROCESS_STOPPED',
                     'M0_CONF_HA_PROCESS_DTM_RECOVERED')


ha_conf_obj_states = ('M0_NC_UNKNOWN',
                      'M0_NC_ONLINE',
                      'M0_NC_FAILED',
                      'M0_NC_TRANSIENT',
                      'M0_NC_REPAIR',
                      'M0_NC_REPAIRED',
                      'M0_NC_REBALANCE',
                      'M0_NC_DTM_RECOVERING')


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
            state: HaxGlobalState = inject.instance(HaxGlobalState)
            while (True):
                try:
                    return f(*args, **kwds)
                except HAConsistencyException as e:
                    if state.is_stopping():
                        LOG.warning(
                            'HAConsistencyException will not cause '
                            'automatic retries: application is exiting.')
                        raise e
                    attempt_count += 1
                    if max_retries >= 0 and attempt_count > max_retries:
                        LOG.warning(
                            'Function %s: Too many errors happened in a row '
                            '(max_retries = %d)', f.__name__, max_retries)
                        raise e
                    LOG.debug(
                        f'Got HAConsistencyException: {e.message} while '
                        f'invoking function {f.__name__} '
                        f'(attempt {attempt_count}). The attempt will be '
                        f'repeated in {wait_seconds} seconds')
                    sleep(wait_seconds)

        return wrapper

    return callable


TxPutKV = NamedTuple('TxPutKV', [('key', str), ('value', str),
                                 ('cas', Optional[Any])])

PutKV = NamedTuple('PutKV', [
    ('key', str),
    ('value', str)
])


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

    @uses_consul_cache
    def kv_get(self, key: str, kv_cache=None,
               allow_null=False, **kwargs) -> Any:
        LOG.debug('KVGET key=%s, kwargs=%s', key, kwargs)
        data = self.kv_get_raw(key, **kwargs)[1]
        if data is None and allow_null is False:
            raise HAConsistencyException('Could not get data from Consul KV')
        return data

    @invalidates_consul_cache
    def kv_put(self, key: str, data: str, kv_cache=None, **kwargs) -> bool:
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

    def get_node_names(self) -> List[str]:
        """
        Return full list of service names currently registered in Consul
        server.
        """
        try:
            node_names: List[str] = []
            nodes: List[Dict[str, Any]] = self.cns.catalog.nodes()[1]
            for node in nodes:
                node_names.append(str(node['Node']))
            return node_names
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                'Cannot access Consul catalog') from e

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
        self.lock = Lock()
        self.object_state_getters = {
            ObjT.SDEV.name: self.get_sdev_state,
            ObjT.DRIVE.name: self.get_sdev_state,
            ObjT.NODE.name: self.get_node_state,
            ObjT.ENCLOSURE.name: self.get_encl_state,
            ObjT.CONTROLLER.name: self.get_ctrl_state
        }

    def get_consul_node(self, node: str) -> Optional[str]:
        LOG.debug('fetching consul node for node: %s', node)
        consul_node_data = self.kv.kv_get(f'consul/node/{node}',
                                          allow_null=True)
        if consul_node_data:
            consul_node_val: bytes = consul_node_data['Value']
            consul_node = consul_node_val.decode('utf-8')
            LOG.debug('consul node %s node: %s', consul_node, node)
            return consul_node
        return None

    def _service_by_name(self, hostname: str,
                         svc_name: str) -> Optional[Dict[str, Any]]:
        cat = self.catalog
        consul_node = self.get_consul_node(hostname)
        if not consul_node or consul_node is None:
            return None
        LOG.debug('consul_node: %s node: %s', consul_node, hostname)
        for svc in cat.get_services(svc_name):
            if str(svc['Node']) in consul_node:
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
            return consul_to_local_nodename(str(local_nodename))
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate '
                                         'to Consul Agent') from e

    @repeat_if_fails()
    def force_leave(self, node: str):
        try:
            self.cns.agent.force_leave(node)
        except Exception as e:
            raise HAConsistencyException('Force leaving agent') from e

    @uses_consul_cache
    def _local_service_by_name(self,
                               name: str,
                               kv_cache=None) -> Optional[Dict[str, Any]]:
        """
        Returns the service data by its name assuming that it runs at the same
        node to the current hax process.
        """
        local_nodename = self.get_local_nodename()
        return self._service_by_name(local_nodename, name)

    @uses_consul_cache
    def _service_data(self, kv_cache=None) -> ServiceData:
        my_fidk = self.get_hax_fid(kv_cache=kv_cache).key
        services = self.catalog.get_services('hax')
        for svc in services:
            if int(svc['ServiceID']) == my_fidk:
                return mkServiceData(svc)
        raise RuntimeError('Unreachable')

    @uses_consul_cache
    def get_hax_fid(self, kv_cache=None) -> Fid:
        """
        Returns the fid of the current hax process (in other words, returns
        "my own" fid)
        """
        svc: Optional[Dict[str, Any]] = self._local_service_by_name('hax')
        if not svc or svc is None:
            raise HAConsistencyException('Error fetching hax svc')
        return mk_fid(ObjT.PROCESS, int(svc['ServiceID']))

    @uses_consul_cache
    def get_ha_fid(self, kv_cache=None) -> Fid:
        svc = self._local_service_by_name('hax')
        if not svc or svc is None:
            raise HAConsistencyException('Error fetching hax svc')
        return mk_fid(ObjT.SERVICE, int(svc['ServiceID']) + 1)

    @repeat_if_fails()
    @uses_consul_cache
    def get_rm_fid(self, kv_cache=None) -> Fid:
        rm_node = self.get_session_node(self.get_leader_session())
        confd = self._service_by_name(rm_node, 'confd')
        if not confd or confd is None:
            raise HAConsistencyException('Error fetching confd svc')
        pfidk = int(confd['ServiceID'])
        fidk = self.kv.kv_get(f'm0conf/nodes/{rm_node}/processes/{pfidk}/'
                              'services/rms', kv_cache=kv_cache)
        return mk_fid(ObjT.SERVICE, int(fidk['Value']))

    @uses_consul_cache
    def get_hax_endpoint(self, kv_cache=None) -> str:
        hax_ep = self._service_data(kv_cache=kv_cache).address
        if not hax_ep or hax_ep is None:
            raise HAConsistencyException('Error fetching hax endpoint')
        return hax_ep

    @uses_consul_cache
    @repeat_if_fails()
    def get_hax_ip_address(self, kv_cache=None) -> str:
        hax_ip = self._service_data(kv_cache=kv_cache).ip_addr
        if not hax_ip or hax_ip is None:
            raise HAConsistencyException('Error fetching hax ip address')
        return str(hax_ip)

    @uses_consul_cache
    @repeat_if_fails()
    def get_hax_hostname(self, kv_cache=None) -> str:
        hax_hostname = self._service_data(kv_cache=kv_cache).node
        if not hax_hostname or hax_hostname is None:
            raise HAConsistencyException('Error fetching hax hostname')
        return str(hax_hostname)

    def get_hax_http_port(self) -> int:
        service_data = self._local_service_by_name('hax')
        if not service_data:
            raise HAConsistencyException('Error fetching hax svc')
        return int(service_data['ServiceMeta'].get('http_port', 8008))

    @repeat_if_fails()
    def fid_to_endpoint(self, proc_fid: Fid) -> Optional[str]:
        pfidk = int(proc_fid.key)
        # process_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        process_items = self.get_all_nodes()
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

        leader = self.kv.kv_get('leader', allow_null=True)
        if leader is None:
            raise HAConsistencyException('No leader key exists yet')

        node: bytes = leader['Value']
        if node is None:
            raise HAConsistencyException('No RC leader found')

        return node.decode('utf-8')

    @repeat_if_fails()
    def get_leader_session(self) -> str:
        """
        Blocking version of `get_leader_session_no_wait()`.
        The method either returns the RC leader session or blocks until the
        session becomes available.
        """
        return str(self.get_leader_session_no_wait())

    def get_leader_session_no_wait(self) -> str:
        """
        Returns the RC leader session. HAConsistencyException is raised
        immediately if there is no RC leader selected at the moment.
        """
        try:
            leader = self.kv.kv_get('leader')
            return str(leader['Session'])
        except KeyError:
            raise HAConsistencyException(
                'Could not get the leader from Consul')

    def is_leader_value_present_for_session(self) -> bool:
        leader = self.kv.kv_get('leader', allow_null=True)
        if leader is None:
            return False

        node: bytes = leader['Value']
        if node is None:
            return False
        return True

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

    @repeat_if_fails()
    @uses_consul_cache
    def get_all_nodes(self, kv_cache=None):
        node_items = self.kv.kv_get('m0conf/nodes',
                                    recurse=True,
                                    kv_cache=kv_cache)
        return node_items

    def get_session_node(self, session_id: str) -> str:
        try:
            session = self.cns.session.info(session_id)[1]
            if session is None or session.get('Node') is None:
                raise HAConsistencyException('Failed to get session'
                                             ' node')
            # Principal RM
            return consul_to_local_nodename(str(session['Node']))
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate to'
                                         ' Consul Agent') from e

    def get_svc_status(self, srv_fid: Fid, kv_cache=None) -> str:
        try:
            return self.get_process_status(srv_fid,
                                           kv_cache=kv_cache).proc_status
        except Exception:
            return 'Unknown'

    @supports_consul_cache
    def get_m0d_statuses(self,
                         motr_services=None,
                         kv_cache=None
                         ) -> List[Tuple[ServiceData, ObjHealth]]:
        """
        Return the list of all Motr service statuses according to Consul
        watchers.The following services are considered [default]: ios, confd.
        """
        if not motr_services:
            motr_services = set(['ios', 'confd'])
        result = []
        for service_name in self.catalog.get_service_names():
            if service_name not in motr_services:
                continue
            data = self.get_service_data_by_name(service_name)
            LOG.log(TRACE, 'svc data: %s', data)
            for item in data:
                node = self.get_process_node(item.fid, kv_cache=kv_cache)
                svc_health = self.get_service_health(node,
                                                     item.fid.key,
                                                     kv_cache=kv_cache)
                result += [(item, svc_health)]
        return result

    def get_service_data_by_name(self, name: str) -> List[ServiceData]:
        services = self.catalog.get_services(name)
        LOG.log(TRACE, 'Services "%s" received: %s', name, services)
        services_dict = {}
        for svc in services:
            services_dict[int(svc['ServiceID'])] = mkServiceData(svc)
        return [services_dict[key] for key in services_dict]

    def get_confd_list(self) -> List[ServiceData]:
        return self.get_service_data_by_name('confd')

    def get_proc_fids_with_status(self,
                                  proc_names: List[str]
                                  ) -> List[Tuple[Fid, ObjHealth]]:
        """
        Fetches all the process fids and their statuses across the cluster
        for a given process name.
        """
        statuses = self.get_m0d_statuses(proc_names)
        LOG.debug('The following statuses received for %s: %s',
                  proc_names, statuses)
        return [(item.fid, status) for item, status in statuses]

    @uses_consul_cache
    def get_services_by_parent_process(self,
                                       process_fid: Fid,
                                       kv_cache=None) -> List[FidWithType]:
        # node_items = self.kv.kv_get('m0conf/nodes',
        #                             recurse=True,
        #                             kv_cache=kv_cache)
        node_items = self.get_all_nodes(kv_cache=kv_cache)
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
        # node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        node_items = self.get_all_nodes()
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
        # node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        node_items = self.get_all_nodes()
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
    @uses_consul_cache
    def get_conf_obj_status_failvec(self,
                                    obj_fid: Fid,
                                    kv_cache=None) -> int:
        to_ha_state_map = {
            'unknown': HaNoteStruct.M0_NC_TRANSIENT,
            'online': HaNoteStruct.M0_NC_ONLINE,
            'offline': HaNoteStruct.M0_NC_TRANSIENT,
            'failed': HaNoteStruct.M0_NC_FAILED,
            'dtm_recovering': HaNoteStruct.M0_NC_DTM_RECOVERING,
            'm0_conf_ha_process_starting': HaNoteStruct.M0_NC_TRANSIENT,
            'm0_conf_ha_process_started': HaNoteStruct.M0_NC_DTM_RECOVERING,
            'm0_conf_ha_process_stopping': HaNoteStruct.M0_NC_TRANSIENT,
            'm0_conf_ha_process_stopped': HaNoteStruct.M0_NC_TRANSIENT,
            'm0_conf_ha_process_dtm_recovered':
            HaNoteStruct.M0_NC_ONLINE}

        obj_state = 'online'
        if (obj_fid.container == ObjT.PROCESS.value):
            status = self.get_process_status(obj_fid)
            obj_state = 'unknown'
            if status.proc_type == m0HaProcessType.M0_CONF_HA_PROCESS_M0D.name:
                obj_state = status.proc_status
            LOG.debug('Got process obj state: %s', obj_state)
            if (obj_state ==
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED.name and
                    self.is_process_confd(obj_fid)):
                return HaNoteStruct.M0_NC_ONLINE
        else:
            failvec_data = self.kv.kv_get('failvec', kv_cache=kv_cache)
            failvec = failvec_data['Value']
            if failvec:
                obj_state = failvec.get(f'{obj_fid}')
        return to_ha_state_map[str(obj_state).lower()]

    @repeat_if_fails()
    def is_process_confd(self, proc_fid: Fid, kv_cache=None) -> bool:
        confds = self.get_confd_list()
        for confd in confds:
            if proc_fid == confd.fid:
                return True
        return False

    @repeat_if_fails()
    @uses_consul_cache
    def get_conf_obj_status(self,
                            obj_t: ObjT,
                            fidk: int,
                            kv_cache=None) -> int:

        obj_state: int = HaNoteStruct.M0_NC_ONLINE
        if obj_t.name in (ObjT.PROCESS.name, ObjT.SERVICE.name):
            # 'node/<node_name>/process/<process_fidk>/service/type'
            node_items = self.get_all_nodes(kv_cache=kv_cache)
            # TODO [KN] This code is too cryptic. To be refactored.
            keys = getattr(self, 'get_{}_keys'.format(obj_t.name.lower()))(
                node_items, fidk)
            if len(keys) != 1:
                raise RuntimeError(f'XXX fidk:{fidk} len:{len(keys)}')
            key = keys[0].split('/')
            node_key = ('/'.join(key[:3]))
            node_val = self.kv.kv_get(node_key, kv_cache=kv_cache)
            data = node_val['Value']
            node_name: str = json.loads(data)['name']
            if (self.get_node_health_status(node_name, kv_cache=kv_cache) !=
                    'passing'):
                obj_state = ObjHealth.OFFLINE.to_ha_note_status()

        device_obj_types = self.object_state_getters
        if obj_t.name in (ObjT.PROCESS.name, ObjT.SERVICE.name):
            obj_state = self.get_proc_svc_conf_obj_status(obj_t,
                                                          fidk,
                                                          kv_cache=kv_cache)

        elif obj_t.name in device_obj_types:
            obj_state = device_obj_types[obj_t.name](obj_t,
                                                     fidk,
                                                     kv_cache=kv_cache)

        return obj_state

    @uses_consul_cache
    def get_proc_svc_conf_obj_status(self,
                                     obj_t: ObjT,
                                     fidk: int,
                                     kv_cache=None) -> int:
        if ObjT.SERVICE.name == obj_t.name:
            svc_fid = create_service_fid(fidk)
            pfid = self.get_service_process_fid(svc_fid, kv_cache=kv_cache)
        else:
            pfid = create_process_fid(fidk)
        proc_node = self.get_process_node(pfid, kv_cache=kv_cache)
        # local_node = self.get_local_nodename()
        # Every motr process requests the entire cluster status, thus if
        # its the requesting process is the same as the processing one,
        # we just reply itself as ONLINE instead of running self checks.
        # if proc_node == local_node:
        #     return HaNoteStruct.M0_NC_ONLINE
        proc_status: ObjHealth = self.get_service_health(proc_node, pfid.key,
                                                         kv_cache=kv_cache)
        # Report ONLINE for hax and confd if they are already started.
        hax_fid = self.get_hax_fid(kv_cache=kv_cache)
        if (proc_status == ObjHealth.RECOVERING and
                (self.is_process_confd(pfid) or
                 pfid == hax_fid)):
            return HaNoteStruct.M0_NC_ONLINE
        return proc_status.to_ha_note_status()

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
        LOG.debug('fid: %s, fidk: %d', fid, fidk)
        return [
            x['Key'] for x in node_items
            if f'{fid}' == x['Key'].split('/')[-1]
        ]

    @uses_consul_cache
    def is_node_alive(self, node: str, kv_cache=None) -> bool:
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
                if consul_to_local_nodename(member['Name']) == node:
                    return int(member['Status']) == 1
            return True
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                'Failed to members data from Consul') from e

    @uses_consul_cache
    def get_node_health_details(
            self, node: str,
            kv_cache=None) -> Optional[List[Dict[str, Any]]]:
        """
        Returns the list of health checks (as it is reported by Consul, see
        'Health: node' section at
        https://python-consul.readthedocs.io/en/latest/).
        """
        try:
            consul_node = self.get_consul_node(node)
            if not consul_node or consul_node is None:
                return None
            return self.cns.health.node(consul_node)[1]
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                f'Failed to get {node} node health: {e}')

    @uses_consul_cache
    def get_node_health_status(self, node: str, kv_cache=None) -> str:
        """
        Returns the node health status string returned by Consul.
        Possible return values: passing, warning, critical
        """
        try:
            node_data = self.get_node_health_details(node, kv_cache=kv_cache)
            # if not node_data or (not self.is_node_alive(node,
            #                                             kv_cache=kv_cache)):
            if not node_data:
                return 'offline'
            return str(node_data[0]['Status'])
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                f'Failed to get {node} node health') from e

    @repeat_if_fails()
    @uses_consul_cache
    def get_node_fid(self, node: str, kv_cache=None) -> Optional[Fid]:
        """
        Returns the fid of the given node.

        Parameters:
            node : hostname of the node.
        """
        # Example,
        # m0conf/nodes/
        # 0x6e00000000000001:0x3:{"name": "ssc-vm-1623.colo.seagate.com",
        #                         "state": "M0_NC_UNKNOWN"}
        # node_items = self.kv.kv_get('m0conf/nodes',
        #                             recurse=True,
        #                             kv_cache=kv_cache)
        node_items = self.get_all_nodes(kv_cache=kv_cache)
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
    @uses_consul_cache
    def get_node_name_by_fid(self,
                             node_fid: Fid,
                             kv_cache=None) -> Optional[str]:
        """
        Returns the node name by its FID value or None if the given FID doesn't
        correspond to any node.
        """
        node_data = self.kv.kv_get(f'm0conf/nodes/{node_fid}',
                                   kv_cache=kv_cache)
        if node_data:
            parsed = json.loads(node_data['Value'])
            name: str = parsed['name']
            return name
        return None

    @repeat_if_fails()
    @uses_consul_cache
    def get_node_name_by_machineid(self,
                                   machineid: str,
                                   kv_cache=None,
                                   allow_null=False) -> Optional[str]:
        """
        Returns the node name by its machine id value or None if the given
        machine id doesn't correspond to any node.
        """
        mid_key = self.kv.kv_get(machineid, kv_cache=kv_cache,
                                 allow_null=allow_null)
        if mid_key:
            name: bytes = mid_key['Value']
            return name.decode('utf-8')
        return None

    @repeat_if_fails()
    @uses_consul_cache
    def get_node_ctrl_fids(self,
                           node: str,
                           kv_cache=None) -> Optional[List[Fid]]:
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
        encl_fid = self.get_node_encl_fid(node, kv_cache=kv_cache)
        if not encl_fid:
            return None
        ctrl_items = self.get_all_sites(kv_cache=kv_cache)
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

    def get_node_hare_motr_s3_fids(self, node: str) -> List[Fid]:
        """
        Parameters:
            node : hostname of the node
        response:
            returns list of fids for hax, ioservices, confd and s3services
            configured and running on @node.
        """
        services = ['hax', 'ios', 'confd', 's3service']
        node_data = self.get_node_health_details(node)
        fids: List[Fid] = []
        if not node_data:
            return []
        for item in node_data:
            if item['ServiceName'] in services:
                fids.append(mk_fid(ObjT.PROCESS, int(item['ServiceID'])))
        return fids

    @repeat_if_fails()
    @uses_consul_cache
    def get_io_service_devices(self,
                               ioservice_fid: Fid,
                               kv_cache=None) -> Optional[List[str]]:
        if not ioservice_fid:
            return None
        # Example key m0conf/nodes/0x6e00000000000001:0x3/processes/
        #   0x7200000000000001:0x15/services/0x7300000000000001:0x17/sdevs/
        #   0x6400000000000001:0x18:{"path": "/dev/sdc", "state": "offline"}
        # sdev_items = self.kv.kv_get('m0conf/nodes',
        #                             recurse=True,
        #                             kv_cache=kv_cache)

        sdev_items = self.get_all_nodes(kv_cache=kv_cache)
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
    @uses_consul_cache
    def get_all_sites(self, kv_cache=None):
        return self.kv.kv_get('m0conf/sites', recurse=True, kv_cache=kv_cache)

    @repeat_if_fails()
    @uses_consul_cache
    def get_device_controller(self, sdev_fid, kv_cache=None):
        # Example key m0conf/sites/0x5300000000000001:0x1/racks/
        #    0x6100000000000001:0x2/encls/0x6500000000000001:0x4/ctrls/
        #    0x6300000000000001:0x5/drives/0x6b00000000000001:0x38:
        #    {"sdev": "0x6400000000000001:0x37", "state": "M0_NC_UNKNOWN"}
        sites_items = self.get_all_sites(kv_cache=kv_cache)

        for item in sites_items:
            if 'sdev' not in json.loads(item['Value']).keys():
                continue

            if json.loads(item['Value'])['sdev'] == f'{sdev_fid}':
                key = item['Key'].split('/')
                return key[8]

        return None

    @repeat_if_fails()
    @uses_consul_cache
    def get_ioservice_ctrl_fid(self,
                               ioservice_fid: Fid,
                               kv_cache=None) -> Optional[Fid]:
        """
        Returns the fid of the controller for the given IOservice.

        Parameters:
            ioservice_fid : Fid of IO service for which ctrl fid is required.

        TODO: Instead of comparing devices, add a mapping from controller
              to I/O service
        """
        if not ioservice_fid:
            return None

        sdev_fids = self.get_io_service_devices(ioservice_fid,
                                                kv_cache=kv_cache)

        if not sdev_fids:
            return None

        sdev_fid = sdev_fids[0]

        ctrl_fid = self.get_device_controller(sdev_fid, kv_cache=kv_cache)

        if ctrl_fid is None:
            return None
        else:
            return Fid.parse(ctrl_fid)

    @repeat_if_fails()
    def all_io_services_failed(self, node: str, kv_cache=None) -> bool:
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
                                     recurse=True,
                                     kv_cache=kv_cache)
        for item in sites_items:
            if 'name' not in json.loads(item['Value']).keys():
                continue

            if json.loads(item['Value'])['name'] == 'ios':
                # m0conf/nodes/0x6e00000000000001:0x3/processes/
                # 0x7200000000000001:0xa:
                # {"name": "m0_server", "state": "online"}
                p_fid = item['Key'].split('/')[4]
                p_key = f"m0conf/nodes/{node_fid}/processes/{p_fid}"
                process = self.kv.kv_get(p_key,
                                         recurse=False,
                                         kv_cache=kv_cache)

                state = json.loads(process['Value'])['state']
                if state not in ('stopped', 'failed', 'offline'):
                    return False

        return True

    # TO_BE_USED: This function can be used in future
    @repeat_if_fails()
    def check_resource_status(self,
                              resource_type: ObjT,
                              fid: str,
                              status: str,
                              kv_cache=None) -> Optional[bool]:
        """
        Checks if all the motr services of given node are in given state.
        Motr services include 'ios' and 'confd'
        """

        status_map = {ObjStatus(resource_type=ObjT.NODE,
                                status='online'):
                      'M0_CONF_HA_PROCESS_STARTED'}

        if resource_type is ObjT.NODE:
            children = self.kv.kv_get(f'm0conf/nodes/{fid}/processes',
                                      recurse=True,
                                      kv_cache=kv_cache)
            search_filter: List[str] = ['ios', 'confd']
        else:
            return None

        for item in children or []:
            if 'name' not in json.loads(item['Value']).keys():
                continue

            if json.loads(item['Value'])['name'] not in search_filter:
                continue

            # m0conf/nodes/0x6e00000000000001:0x3/processes/
            # 0x7200000000000001:0xa:
            # {"name": "m0_server", "state": "online"}
            p_fid = item['Key'].split('/')[4]
            p_key = f"processes/{p_fid}"
            process = self.kv.kv_get(p_key,
                                     recurse=False,
                                     kv_cache=kv_cache)

            if not process:
                return False

            state = json.loads(process['Value'])['state']
            if status == 'online':
                if (state !=
                        status_map[ObjStatus(resource_type=resource_type,
                                             status='online')]):
                    return False

        return True

    @repeat_if_fails()
    @uses_consul_cache
    def get_node_encl_fid(self, node: str, kv_cache=None) -> Optional[Fid]:
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
        node_fid = self.get_node_fid(node, kv_cache=kv_cache)
        if not node_fid:
            return None
        encl_items = self.kv.kv_get('m0conf/sites',
                                    recurse=True,
                                    kv_cache=kv_cache)
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

    def get_device_ha_state(self, status: ObjHealth) -> str:

        device_ha_state_map = {
            ObjHealth.UNKNOWN: m0HaObjState.M0_NC_TRANSIENT,
            ObjHealth.OK: m0HaObjState.M0_NC_ONLINE,
            ObjHealth.OFFLINE: m0HaObjState.M0_NC_TRANSIENT,
            ObjHealth.FAILED: m0HaObjState.M0_NC_FAILED,
            ObjHealth.REPAIR: m0HaObjState.M0_NC_REPAIR,
            ObjHealth.REPAIRED: m0HaObjState.M0_NC_REPAIRED,
            ObjHealth.REBALANCE: m0HaObjState.M0_NC_REBALANCE
            }
        return device_ha_state_map[status].name

    @repeat_if_fails()
    def set_node_state(self,
                       node_fid: Fid,
                       status: ObjHealth,
                       kv_cache=None) -> None:
        # Example,
        # {
        #    "key": "m0conf/nodes/0x6e00000000000001:0x3",
        #    "value": "{\"name\": \"srvnode-1.data.private\",
        #               \"state\": \"M0_NC_UNKNOWN\"}"
        # }
        # node_items = self.kv.kv_get('m0conf/nodes',
        #                             recurse=True,
        #                             kv_cache=kv_cache)
        node_items = self.get_all_nodes(kv_cache=kv_cache)
        regex = re.compile(f'^m0conf/nodes/{node_fid}$')
        for node in node_items:
            match_result = re.match(regex, node['Key'])
            if not match_result:
                continue
            value = json.loads(node['Value'])
            value['state'] = self.get_device_ha_state(status)
            LOG.debug('Setting node=%s in KV with state=%s', node_fid,
                      value['state'])
            self.kv.kv_put(node['Key'], json.dumps(value), kv_cache=kv_cache)

    @repeat_if_fails()
    def set_encl_state(self,
                       encl_fid: Fid,
                       status: ObjHealth,
                       kv_cache=None) -> None:
        # Example,
        # {
        #    "key": "m0conf/sites/0x5300000000000001:0x1/
        #            racks/0x6100000000000001:0x2/encls/
        #            0x6500000000000001:0x4",
        #    "value": "{\"node\": \"0x6e00000000000001:0x3\",
        #               \"state\": \"M0_NC_UNKNOWN\"}"
        # }
        node_items = self.get_all_sites(kv_cache=kv_cache)
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
            self.kv.kv_put(encl['Key'], json.dumps(value), kv_cache=kv_cache)

    @repeat_if_fails()
    def get_ctrl_state_updates(self,
                               ctrl_fid: Fid,
                               status: ObjHealth,
                               kv_cache=None) -> List[PutKV]:
        # Example,
        # {
        #    "key": "m0conf/sites/0x5300000000000001:0x1/
        #            racks/0x6100000000000001:0x2/encls/
        #            0x6500000000000001:0x4/ctrls/
        #            0x6300000000000001:0x5",
        #    "value": "{\"state\": \"M0_NC_UNKNOWN\"}"
        # }
        ctrl_items = self.get_all_sites(kv_cache=kv_cache)
        regex = re.compile(f'^m0conf\\/.*\\/ctrls/{ctrl_fid}$')
        result: List[PutKV] = []
        for ctrl in ctrl_items:
            match_result = re.match(regex, ctrl['Key'])
            if not match_result:
                continue
            value = json.loads(ctrl['Value'])
            value['state'] = self.get_device_ha_state(status)
            LOG.debug('Setting ctrl=%s in KV with state=%s', ctrl_fid,
                      value['state'])
            result.append(PutKV(key=ctrl['Key'], value=json.dumps(value)))
        return result

    @repeat_if_fails()
    @uses_consul_cache
    def get_ctrl_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        assert obj_t.value == ObjT.CONTROLLER.value
        ctrl_fid = mk_fid(ObjT.CONTROLLER, fidk)
        ctrl_items = self.get_all_sites(kv_cache=kv_cache)
        regex = re.compile(f'^m0conf\\/.*\\/ctrls/{ctrl_fid}$')
        for ctrl in ctrl_items:
            match_result = re.match(regex, ctrl['Key'])
            if not match_result:
                continue
            val = json.loads(ctrl['Value'])
            state = val['state']
            LOG.debug('Controller=%s state=%s', ctrl_fid, state)
            if state in (m0HaObjState.M0_NC_TRANSIENT.name,
                         m0HaObjState.M0_NC_FAILED.name):
                node = self.get_ctrl_node(ctrl_fid, kv_cache=kv_cache)
                if (self.get_node_health_status(node, kv_cache=kv_cache) ==
                        'passing'):
                    return m0HaObjState.M0_NC_ONLINE
            else:
                return m0HaObjState.parse(state)
        return m0HaObjState.M0_NC_ONLINE

    @repeat_if_fails()
    @uses_consul_cache
    def get_encl_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        assert obj_t.value == ObjT.ENCLOSURE.value
        encl_fid = mk_fid(ObjT.ENCLOSURE, fidk)
        encl_items = self.get_all_sites(kv_cache=kv_cache)
        regex = re.compile(f'^m0conf\\/.*\\/encls/{encl_fid}$')

        for encl in encl_items:
            match_result = re.match(regex, encl['Key'])
            if not match_result:
                continue
            val = json.loads(encl['Value'])
            state = val['state']
            LOG.debug('Enclosure=%s state=%s', encl_fid, state)
            if state in (m0HaObjState.M0_NC_TRANSIENT.name,
                         m0HaObjState.M0_NC_FAILED.name):
                node = self.get_encl_node(encl_fid, kv_cache=kv_cache)
                if (self.get_node_health_status(node, kv_cache=kv_cache) ==
                        'passing'):
                    return m0HaObjState.M0_NC_ONLINE
            else:
                return m0HaObjState.parse(state)
        return m0HaObjState.M0_NC_ONLINE

    @repeat_if_fails()
    @uses_consul_cache
    def get_node_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        assert obj_t.value == ObjT.NODE.value
        node_fid = mk_fid(ObjT.NODE, fidk)
        node = self.kv.kv_get(f'm0conf/nodes/{node_fid}',
                              recurse=False,
                              kv_cache=kv_cache)
        if node:
            val = json.loads(node['Value'])
            state = val['state']
            node_name = val['name']
            LOG.debug('Node=%s state=%s', node_fid, state)
            if state in (m0HaObjState.M0_NC_TRANSIENT.name,
                         m0HaObjState.M0_NC_FAILED.name):
                if (self.get_node_health_status(node_name,
                                                kv_cache=kv_cache) ==
                        'passing'):
                    return m0HaObjState.M0_NC_ONLINE
            else:
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
                           address=f'{srv_address}@{srv_port}')

    def update_fs_stats(self, stats_data: FsStatsWithTime) -> None:
        # TODO investigate whether we can replace json with simplejson in
        # all the cases
        data_str = simplejson.dumps(stats_data)
        self.kv.kv_put('stats/filesystem', data_str)

    def update_pver_bc(self, data: ByteCountStats) -> None:
        """
        Updates bytecount stats per pool versions for all pvers
        under the ios service in consul kv.
        Example: key= ioservices/0x7200000000000001:0xf/pvers/
                      0x7600000000000001:0x8/users/1
        value = {"bc":4096, "object_cnt":1}
        """
        ios_fid = data.proc_fid
        for pver in data.pvers:
            value = json.dumps({'bc': pver.byte_count,
                                'object_cnt': pver.object_count})

            key = f'ioservices/{ios_fid}/pvers/{pver.pver_fid}/' \
                f'users/{pver.user_id}'
            LOG.debug('Setting bytecount stats in KV: %s:%s', key, value)
            self.kv.kv_put(key, value)

    def update_bc_for_dg_category(self,
                                  pver_bc: Dict[str, int],
                                  pver_state: Dict[str, PverInfo]):
        '''
        This function will update bytecount for subsequent dg state/category
        which will reflect on cluster status.
        Bytecount data is stored in consul KV in key:value format
        ioservices/0x7200000000000001:0x20/pvers/0x7600000000000001:0x6/users/1
        value = {"bc": 4096, "object_cnt": 1}
        '''
        pver_state_map = {
            PverState.M0_CPS_HEALTHY: 'healthy',
            PverState.M0_CPS_DEGRADED: 'degraded',
            PverState.M0_CPS_CRITICAL: 'critical',
            PverState.M0_CPS_DAMAGED: 'damaged'
        }
        # Calculate total bytecount based on pver status.
        data: Dict[PverState, int] = {}
        for pver, info in pver_state.items():
            bc = pver_bc.get(pver, 0)
            state = info.state
            if state in data:
                data[state] += bc
            else:
                data[state] = bc
        # Populate the consul kv with total bytecount based on state.
        for state in pver_state_map:
            self.kv.kv_put(f'bytecount/{pver_state_map[state]}',
                           json.dumps(data.get(state, 0)))

    @repeat_if_fails()
    def update_process_status(self, event: ConfHaProcess) -> None:
        assert 0 <= event.chp_event < len(ha_process_events), \
            f'Invalid event type: {event.chp_event}'
        if event.fid == self.get_hax_fid():
            event_type = m0HaProcessType.M0_CONF_HA_PROCESS_HA.name
        else:
            event_type = m0HaProcessType(event.chp_type).name
        data = json.dumps({'state': ha_process_events[event.chp_event],
                           'type': event_type})
        # Maintain statuses for all the motr processes in the cluster
        # for every node so that in case of 1 or more node failures,
        # as every node will receive the node failure event, the failed
        # processes statuses will be updated locally without each node
        # stepping over each other's update and without any need for
        # synchronization.
        key = f'processes/{event.fid}'
        LOG.debug('Setting process status in KV: %s:%s', key, data)
        self.kv.kv_put(key, data)

        self.set_motr_processes_status(str(event.fid), ha_process_events[
                                                  event.chp_event])

    @supports_consul_cache
    def update_drive_state(self,
                           drive_fids: List[Fid],
                           status: ObjHealth,
                           device_event=True,
                           kv_cache=None) -> None:
        device_state_map = {
            ObjHealth.OK: 'online',
            ObjHealth.FAILED: 'failed',
            ObjHealth.OFFLINE: 'offline',
            ObjHealth.REPAIR: 'repairing',
            ObjHealth.REPAIRED: 'repaired',
            ObjHealth.REBALANCE: 'rebalancing'
        }
        updates: List[PutKV] = []
        for drive in drive_fids:
            sdev_fid = self.drive_to_sdev_fid(drive)
            # Note that we don't update KV values within this call
            # but accumulate the changes until we come to the end of the
            # current function. This helps to reuse the kv_cache as long as
            # possible (any kv_put operation will invalidate the current cache)
            updates += self.get_sdev_state_update(sdev_fid,
                                                  device_state_map[status],
                                                  device_event)
        for op in updates:
            self.kv.kv_put(op.key, op.value, kv_cache=kv_cache)

    @repeat_if_fails()
    @supports_consul_cache
    def get_sdev_state_update(self,
                              sdev_fid: Fid,
                              state: str,
                              device_event=True,
                              kv_cache=None) -> List[PutKV]:
        LOG.debug('Setting sdev=%s in KV with state=%s', sdev_fid, state)
        sdev_items = self.get_all_nodes(kv_cache=kv_cache)
        regex = re.compile(f'^m0conf\\/.*\\/sdevs\\/{sdev_fid}$')
        result: List[PutKV] = []
        for sdev in sdev_items:
            match_result = re.match(regex, sdev['Key'])
            if not match_result:
                continue
            value = json.loads(sdev['Value'])
            if not device_event and value['state'] in ('failed',
                                                       'repairing',
                                                       'repaired',
                                                       'rebalancing'):
                continue
            value['state'] = state
            result.append(PutKV(key=sdev['Key'], value=json.dumps(value)))
        return result

    @repeat_if_fails()
    @uses_consul_cache
    def get_sdev_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        drive_to_ha_state_map = {
            'unknown': HaNoteStruct.M0_NC_ONLINE,
            'm0_nc_unknown': HaNoteStruct.M0_NC_ONLINE,
            'online': HaNoteStruct.M0_NC_ONLINE,
            'offline': HaNoteStruct.M0_NC_TRANSIENT,
            'failed': HaNoteStruct.M0_NC_FAILED,
            'repairing': HaNoteStruct.M0_NC_REPAIR,
            'repaired': HaNoteStruct.M0_NC_REPAIRED,
            'rebalancing': HaNoteStruct.M0_NC_REBALANCE}
        if obj_t.name == ObjT.DRIVE.name:
            drive_fid = create_drive_fid(fidk)
            sdev_fid = self.drive_to_sdev_fid(drive_fid, kv_cache=kv_cache)
        else:
            sdev_fid = create_sdev_fid(fidk)
        sdev_items = self.get_all_nodes(kv_cache=kv_cache)
        regex = re.compile(
            f'^m0conf\\/.*\\/sdevs\\/{sdev_fid}$')
        for sdev in sdev_items:
            match_result = re.match(regex, sdev['Key'])
            if not match_result:
                continue
            val = json.loads(sdev['Value'])
            LOG.debug('Sdev=%s state=%s', str(sdev_fid), val['state'])
            return drive_to_ha_state_map[str(val['state']).lower()]

        return HaNoteStruct.M0_NC_ONLINE

    @repeat_if_fails()
    @uses_consul_cache
    def drive_to_sdev_fid(self, drive_fid: Fid, kv_cache=None) -> Fid:
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
        sdev_items = self.kv.kv_get('m0conf/sites',
                                    recurse=True,
                                    kv_cache=kv_cache)
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
        # 1. fetch consul kv for m0conf/nodes recursively,
        #    m0conf/nodes/0x6e00000000000001:0x20/processes/
        #    0x7200000000000001:0x29/services/0x7300000000000001:0x2b/
        #    sdevs/0x6400000000000001:0x2c:
        #    {"path": "/dev/vdf", "state": "M0_NC_UNKNOWN"}
        # 2. shortlist the keys having string `sdevs` in them
        # 3. find drive name in the json value and extract sdev fid from the
        #    key 0x6400000000000001:0x2c
        # 4. Create sdev fid from sdev fid key.
        # sdev_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        node_fid = self.get_node_fid(node_name)
        sdev_items = self.get_all_nodes()
        for x in sdev_items:
            if (f'm0conf/nodes/{node_fid}' in x['Key'] and
                    '/sdevs/' in x['Key']):
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
    @uses_consul_cache
    def get_process_status(self,
                           fid: Fid,
                           proc_node=None,
                           kv_cache=None) -> MotrConsulProcInfo:
        proc_base_fid = self.get_process_base_fid(fid)
        key = f'processes/{proc_base_fid}'
        status = self.kv.kv_get(key, kv_cache=kv_cache, allow_null=True)
        if status:
            val = json.loads(status['Value'])
            return MotrConsulProcInfo(val['state'], val['type'])
        else:
            return MotrConsulProcInfo('Unknown', 'Unknown')

    @uses_consul_cache
    def get_process_status_local(self,
                                 fid: Fid,
                                 proc_node=None,
                                 kv_cache=None) -> MotrConsulProcInfo:
        proc_base_fid = self.get_process_base_fid(fid)
        this_node = self.get_local_nodename()
        key = f'{this_node}/processes/{proc_base_fid}'
        status = self.kv.kv_get(key, kv_cache=kv_cache)
        if status:
            val = json.loads(status['Value'])
            return MotrConsulProcInfo(val['state'], val['type'])
        else:
            return MotrConsulProcInfo('Unknown', 'Unknown')

    @repeat_if_fails()
    def get_process_full_fid(self, proc_base_fid: Fid) -> Optional[Fid]:
        proc_fid = self.kv.kv_get(str(proc_base_fid), recurse=False)
        if proc_fid is not None:
            pfid: Fid = Fid.parse(json.loads(proc_fid['Value']))
            return pfid
        return proc_base_fid

    @repeat_if_fails()
    def get_process_full_fid(self, proc_base_fid: Fid) -> Optional[Fid]:
        proc_fid = self.kv.kv_get(str(proc_base_fid), recurse=False)
        if proc_fid is not None:
            pfid: Fid = Fid.parse(json.loads(proc_fid['Value']))
            return pfid
        return proc_base_fid

    @repeat_if_fails()
    def get_process_full_fid(self, proc_base_fid: Fid) -> Optional[Fid]:
        proc_fid = self.kv.kv_get(str(proc_base_fid), recurse=False)
        if proc_fid is not None:
            pfid: Fid = Fid.parse(json.loads(proc_fid['Value']))
            return pfid
        return proc_base_fid

    def is_proc_local(self, pfid: Fid) -> bool:
        local_node = self.get_local_nodename()
        proc_node = self.get_process_node(pfid)
        return bool(proc_node == local_node)

    @repeat_if_fails()
    def update_process_status_local(self, event: ConfHaProcess) -> None:
        assert 0 <= event.chp_event < len(ha_process_events), \
            f'Invalid event type: {event.chp_event}'
        data = json.dumps({'state': ha_process_events[event.chp_event],
                           'type': m0HaProcessType(event.chp_type).name})
        # Maintain statuses for all the motr processes in the cluster
        # for every node so that in case of 1 or more node failures,
        # as every node will receive the node failure event, the failed
        # processes statuses will be updated locally without each node
        # stepping over each other's update and without any need for
        # synchronization.
        this_node = self.get_local_nodename()
        key = f'{this_node}/processes/{event.fid}'
        LOG.debug('Setting process status locally in KV: %s:%s', key, data)
        self.kv.kv_put(key, data)

    def drive_name_to_id(self, uid: str) -> str:
        drive_id = ''
        # 'm0conf/nodes/<node_name>/processes/<process_fidk>/disks/<disk_uuid>'
        # node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        node_items = self.get_all_nodes()
        for x in node_items:
            if '/disks/' in x['Key'] and uid in x['Key']:
                drive_id = x['Value']
        return drive_id

    def set_m0_disk_state(self,
                          fid: str,
                          objstate: int,
                          kv_cache=None) -> None:
        assert 0 <= objstate < len(ha_conf_obj_states), \
            f'Invalid object state: {objstate}'

        data = json.dumps({'state': ha_conf_obj_states[objstate]})
        key = f'process/{fid}'
        LOG.debug('Setting disk state in KV: %s:%s', key, data)
        self.kv.kv_put(key, data, kv_cache=kv_cache)

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
    #    node status is not 'passing', function returns ObjHealth.FAILED.
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
    def get_service_health(self,
                           node: str,
                           svc_id: int,
                           kv_cache=None) -> ObjHealth:
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
            local_remote_health_ret(ObjHealth.UNKNOWN,
                                    ObjHealth.UNKNOWN),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STOPPING'):
            local_remote_health_ret(ObjHealth.UNKNOWN,
                                    ObjHealth.UNKNOWN),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STARTED'):
            local_remote_health_ret(ObjHealth.RECOVERING,
                                    ObjHealth.RECOVERING),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_DTM_RECOVERED'):
            local_remote_health_ret(ObjHealth.OK,
                                    ObjHealth.OK),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STOPPED'):
            local_remote_health_ret(ObjHealth.OK,
                                    ObjHealth.OK),
            cur_consul_status('passing', 'Unknown'):
            local_remote_health_ret(ObjHealth.OFFLINE,
                                    ObjHealth.OFFLINE),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STOPPING'):
            local_remote_health_ret(ObjHealth.OFFLINE,
                                    ObjHealth.OFFLINE),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STARTED'):
            local_remote_health_ret(ObjHealth.OFFLINE,
                                    ObjHealth.OFFLINE),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_DTM_RECOVERED'):
            local_remote_health_ret(ObjHealth.OFFLINE,
                                    ObjHealth.OFFLINE),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STOPPED'):
            local_remote_health_ret(ObjHealth.OFFLINE,
                                    ObjHealth.OFFLINE),
            cur_consul_status('warning', 'M0_CONF_HA_PROCESS_STARTING'):
            local_remote_health_ret(ObjHealth.OFFLINE,
                                    ObjHealth.OFFLINE),
            cur_consul_status('warning', 'Unknown'):
            local_remote_health_ret(ObjHealth.OFFLINE,
                                    ObjHealth.OFFLINE)}
        try:
            node_data = self.get_node_health_details(
                node, kv_cache=kv_cache)
            if not node_data:
                return ObjHealth.OFFLINE
            node_status = str(node_data[0]['Status'])
            # if node_status != 'passing' or (not self.is_node_alive(
            if node_status != 'passing':
                return ObjHealth.OFFLINE
            status = ObjHealth.UNKNOWN
            for item in node_data:
                if item['ServiceID'] == str(svc_id):
                    pfid = create_process_fid(svc_id)
                    LOG.debug('item.status %s', item['Status'])
                    if item['Status'] in ('critical', 'warning'):
                        return ObjHealth.OFFLINE
                    cns_status = self.get_process_status(pfid,
                                                         kv_cache=kv_cache)
                    svc_health = svc_to_motr_status_map[MotrConsulProcStatus(
                                         item['Status'],
                                         cns_status.proc_status)]
                    LOG.debug('consul.status %s svc_health: %s',
                              cns_status, svc_health)
                    local_node = self.get_local_nodename()
                    proc_node = self.get_process_node(pfid, kv_cache=kv_cache)
                    if proc_node == local_node:
                        status = svc_health.motr_proc_status_local
                    else:
                        status = svc_health.motr_proc_status_remote
                    return status
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate '
                                         'to Consul Agent') from e
        return status

    @repeat_if_fails()
    @uses_consul_cache
    def get_process_node(self, proc_fid: Fid, kv_cache=None) -> str:
        try:
            proc_base_fid = self.get_process_base_fid(proc_fid)
            fidk = proc_base_fid.key
            # 'node/<node_name>/process/<process_fidk>/service/type'
            # node_items = self.kv.kv_get('m0conf/nodes',
            #                             recurse=True,
            #                             kv_cache=kv_cache)
            node_items = self.get_all_nodes(kv_cache=kv_cache)
            LOG.log(TRACE, 'node items: %s', node_items)
            if ObjT.PROCESS.value == proc_base_fid.container:
                keys = self.get_process_keys(node_items, fidk)
            elif ObjT.SERVICE.value == proc_base_fid.container:
                keys = self.get_service_keys(node_items, fidk)
            LOG.debug('proc_fid: %s keys: %s', proc_base_fid, keys)
            if not keys:
                raise HAConsistencyException('Failed to get process node')
            key = keys[0].split('/')
            node_key = ('/'.join(key[:3]))
            node_val = self.kv.kv_get(node_key, kv_cache=kv_cache)
            data = node_val['Value']
        except Exception as e:
            raise HAConsistencyException('failed to get process node') from e
        return str(json.loads(data)['name'])

    @repeat_if_fails()
    @uses_consul_cache
    def get_encl_node(self, encl: Fid, kv_cache=None) -> str:
        # 'node/<node_name>/process/<process_fidk>/service/type'
        site_items = self.kv.kv_get('m0conf/sites',
                                    recurse=True,
                                    kv_cache=kv_cache)
        LOG.debug('site_items: %s', site_items)
        encl_key = [
            x['Key'] for x in site_items
            if f'{encl}' == x['Key'].split('/')[-1]
        ]

        LOG.debug('encl_key: %s', encl_key)
        encl_val = self.kv.kv_get(encl_key[0], kv_cache=kv_cache)
        data = encl_val['Value']
        node_fid = str(json.loads(data)['node'])
        node_val = self.kv.kv_get(f'm0conf/nodes/{node_fid}',
                                  kv_cache=kv_cache)
        node_data = node_val['Value']
        node_name = str(json.loads(node_data)['name'])
        LOG.debug('encl fid: %s node fid: %s node_name:%s',
                  encl, node_fid, node_name)
        return node_name

    @repeat_if_fails()
    @uses_consul_cache
    def get_ctrl_encl(self, ctrl: Fid, kv_cache=None) -> Fid:
        site_items = self.kv.kv_get('m0conf/sites',
                                    recurse=True,
                                    kv_cache=kv_cache)
        ctrl_keys = [
            x['Key'] for x in site_items
            if f'{ctrl}' == x['Key'].split('/')[-1]
        ]
        encl_fid_str = ctrl_keys[0].split('/')[6]
        encl_fid = Fid.parse(encl_fid_str)

        LOG.debug('ctrl fid: %s encl fid: %s',
                  ctrl, encl_fid)
        return encl_fid

    @uses_consul_cache
    def get_ctrl_node(self, ctrl: Fid, kv_cache=None) -> str:
        # 'node/<node_name>/process/<process_fidk>/service/type'
        encl_fid = self.get_ctrl_encl(ctrl, kv_cache=kv_cache)
        node_name = self.get_encl_node(encl_fid, kv_cache=kv_cache)
        LOG.debug('ctrl fid: %s encl fid: %s node_name:%s',
                  ctrl, encl_fid, node_name)

        return str(node_name)

    def get_service_process_fid(self, svc_fid: Fid, kv_cache=None) -> Fid:
        assert ObjT.SERVICE.value == svc_fid.container
        # node_items = self.kv.kv_get('m0conf/nodes',
        #                             recurse=True,
        #                             kv_cache=kv_cache)
        node_items = self.get_all_nodes(kv_cache=kv_cache)
        keys = self.get_service_keys(node_items, svc_fid.key)
        if len(keys) != 1:
            raise RuntimeError(f'svc_fid:{svc_fid} len:{len(keys)}')
        process_fid: str = keys[0].split('/')[4]
        pfid = Fid.parse(process_fid)
        return pfid

    @repeat_if_fails()
    @uses_consul_cache
    def get_profiles(self, kv_cache=None) -> List[Profile]:
        def to_profile(k: str, v: Dict[str, Any]) -> Profile:
            return Profile(fid=Fid.parse(k),
                           name=v['name'],
                           pool_names=v['pools'])

        result: List[Profile] = []
        for x in self.kv.kv_get('m0conf/profiles/',
                                recurse=True,
                                kv_cache=kv_cache):
            fidstr = x['Key'].split('/')[-1]
            payload = simplejson.loads(x['Value'])
            result.append(to_profile(fidstr, payload))
        return result

    @repeat_if_fails()
    def ensure_ioservices_running(self) -> List[bool]:
        statuses = self.get_m0d_statuses()
        LOG.debug('The following statuses received: %s', statuses)
        # started = ['M0_CONF_HA_PROCESS_STARTED' == v[1] for v in statuses]
        started = [ObjHealth.OK == v[1] for v in statuses]
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
        stopping = [v[1] in (ObjHealth.OFFLINE,
                             ObjHealth.STOPPED) for v in statuses]
        return all(stopping)

    def get_process_current_status(self, status_reported: ObjHealth,
                                   proc_fid: Fid) -> ObjHealth:
        status_current = status_reported
        # Reconfirm the process status only if the reported status is FAILED.
        node = self.get_process_node(proc_fid)
        status_current = self.get_service_health(node,
                                                 proc_fid.key)
        LOG.info('node: %s proc: %s current status: %s',
                 node, proc_fid, status_current)
        return status_current

    def svcHealthToM0Status(self, svc_health: ObjHealth):
        svcHealthToM0status: dict = {
            ObjHealth.OK: m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED,
            ObjHealth.FAILED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ObjHealth.UNKNOWN: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ObjHealth.STOPPED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED
        }
        return svcHealthToM0status[svc_health]

    def service_health_to_m0dstatus_update(self, proc_fid: Fid,
                                           svc_health: ObjHealth):
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
                          state: ObjHealth) -> None:
        LOG.debug('Setting process=%s in KV with state=%s',
                  process_fid, state)
        process_state_map = {
            ObjHealth.OK: 'online',
            ObjHealth.FAILED: 'failed',
            ObjHealth.OFFLINE: 'offline',
            ObjHealth.UNKNOWN: 'unknown',
            ObjHealth.STOPPED: 'stopped',
            ObjHealth.RECOVERING: 'dtm_recovering'
        }
        proc_base_fid = self.get_process_base_fid(process_fid)

        # Example key is as follows
        # m0conf/nodes/0x6e00000000000001:0x3/processes/0x7200000000000001:
        # 0x15:{"name": "m0_server", "state": "M0_NC_UNKNOWN"}
        # node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        node_items = self.get_all_nodes()
        regex = re.compile(
            f'^m0conf\\/nodes\\/.*\\/processes\\/{proc_base_fid}$')
        for item in node_items:
            match_result = re.match(regex, item['Key'])
            if not match_result:
                continue
            value = json.loads(item['Value'])
            value['state'] = process_state_map[state]
            LOG.debug('set_process_state: %s', json.dumps(value))
            self.kv.kv_put(item['Key'], json.dumps(value))

    @repeat_if_fails()
    def cleanup_node_process_states(self):
        keys: List[KeyDelete] = [
            KeyDelete(name='processes/', recurse=True),
        ]
        logging.info('Deleting Hare KV entries (%s)', keys)
        if not self.kv.kv_delete_in_transaction(keys):
            raise HAConsistencyException('KV deletion failed')

    @repeat_if_fails()
    def get_configpath(self, allow_null=False):
        logging.info('Getting config_path')
        config_path = self.kv.kv_get('config_path', allow_null=allow_null)

        if config_path is None:
            return None
        return config_path['Value'].decode("utf-8")

    def am_i_rc(self):
        # The call is already marked with @repeat_if_fails
        leader = self.get_leader_node()
        # The call doesn't communicate via Consul REST API
        this_node = self.get_local_nodename()
        return leader == this_node

    @repeat_if_fails()
    def init_motr_processes_status(self):
        local_node = self.get_local_nodename()
        fid = self.get_node_fid(local_node)
        if not fid or fid is None:
            raise HAConsistencyException(
                f'node fid not available yet for {local_node}')
        children = self.kv.kv_get(f'm0conf/nodes/{fid}/processes',
                                  recurse=True)
        for item in children or []:
            if 'name' not in json.loads(item['Value']).keys():
                continue

            # m0conf/nodes/0x6e00000000000001:0x3/processes/
            # 0x7200000000000001:0xa:
            # {"name": "m0_server", "state": "online"}
            if len(item['Key'].split('/')) != 5:
                continue

            p_fid = item['Key'].split('/')[4]
            self.set_motr_processes_status(str(p_fid), ha_process_events[3],
                                           True)

    def get_local_node_status(self):
        total_processes = 0
        started_processes = 0
        for item in self.get_motr_processes_status().values():
            total_processes += 1
            # Checking if status is M0_CONF_HA_PROCESS_STARTED
            if item == ha_process_events[1]:
                started_processes += 1

        if total_processes == started_processes:
            return 'online'
        elif started_processes == 0:
            return 'offline'
        else:
            return 'degraded'

    def get_motr_processes_status(self):
        with self.lock:
            LOG.debug('Current motr_processes_status: %s',
                      motr_processes_status)
            return motr_processes_status

    # bAdd indicate whether new entry should be added or status should be
    # updated only if fid is already present
    def set_motr_processes_status(self, fid, status, bAdd=False):
        with self.lock:
            if fid in motr_processes_status or bAdd:
                motr_processes_status[fid] = status
            LOG.debug('Updated motr_processes_status: %s',
                      motr_processes_status)

    @repeat_if_fails()
    def process_dynamic_fidk_lock(self) -> bool:
        # Acquire lock to update last_updated_base_fidk.
        # This will block until lock is acquired.
        # Will break if any other exception than
        # HAConsistencyException occurs.
        try:
            while not self.kv.kv_put('fidk_update_lock', 'true', cas=0):
                sleep(1)
            return True
        except Exception:
            return False

    @repeat_if_fails()
    def process_dynamic_fidk_unlock(self):
        # Release fidk_update_lock.
        # This will block until released.
        try:
            keys: List[KeyDelete] = [
                KeyDelete(name='fidk_update_lock', recurse=True),
            ]
            while not self.kv.kv_delete_in_transaction(keys):
                sleep(1)
        except Exception:
            raise RuntimeError('Unreachable')

    @repeat_if_fails()
    def get_process_next_dynamic_fidk_lock(self) -> int:
        if self.process_dynamic_fidk_lock():
            fidk = self.kv.kv_get('last_dynamic_fid_key/process',
                                  recurse=False)
            new_fidk = int(json.loads(fidk['Value'])) + 1
            # Update dynamic fid key.
            while not self.kv.kv_put('last_dynamic_fid_key/process',
                                     json.dumps(str(new_fidk))):
                sleep(1)
            self.process_dynamic_fidk_unlock()
        return new_fidk

    @repeat_if_fails()
    def alloc_next_process_fid(self, process_fid: Fid) -> Fid:
        next_fidk = self.get_process_next_dynamic_fidk_lock()
        fid_mask: Fid = ObjTMaskMap[ObjT.PROCESS]
        fid_cont = process_fid.container
        fid_key = process_fid.key + ((fid_mask.key * next_fidk) + next_fidk)
        new_proc_fid = Fid(fid_cont, fid_key)
        base_fid = self.get_process_base_fid(new_proc_fid)
        # Save base fid to actualy fid mapping in Consul.
        while not self.kv.kv_put(f'{base_fid}',
                                 json.dumps(str(new_proc_fid))):
            sleep(1)
        return new_proc_fid

    def get_process_base_fid(self, proc_fid: Fid) -> Fid:
        fid_mask: Fid = ObjTMaskMap[ObjT.PROCESS]
        base_fid = Fid(proc_fid.container,
                       (proc_fid.key & fid_mask.key))
        return base_fid


def dump_json(obj) -> str:
    """
    Interface wrapper to automatically apply correct parameters for json
    serialization obj.
    """
    return simplejson.dumps(obj, for_json=True)
