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
import logging
from base64 import b64encode
from functools import wraps
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from threading import Event, Lock
from time import sleep

import simplejson
from consul import Consul, ConsulException
from consul.base import ClientError
from requests.exceptions import RequestException
from urllib3.exceptions import HTTPError

from hax.common import HaxGlobalState
from hax.exception import HAConsistencyException, InterruptedException
from hax.types import (Fid, ObjT, ObjHealth,
                       ObjTMaskMap, KeyDelete)

from hax.consul.cache import (uses_consul_cache, invalidates_consul_cache)

__all__ = ['create_process_fid', 'create_service_fid',
           'create_sdev_fid', 'create_drive_fid']

LOG = logging.getLogger('hax')

motr_processes_lock = Lock()
motr_processes_status: dict = {}

# XXX What is the difference between `ip_addr` and `address`?
# The names are hard to discern.
ServiceData = NamedTuple('ServiceData', [('node', str), ('fid', Fid),
                                         ('ip_addr', str), ('address', str)])

FidWithType = NamedTuple('FidWithType', [('fid', Fid), ('service_type', str)])


MotrConsulProcInfo = NamedTuple('MotrConsulProcInfo', [('proc_status', str),
                                                       ('proc_type', str)])

MotrConsulProcStatus = NamedTuple(
    "MotrConsulProcStatus", [
        ("consul_svc_status", str),
        ("consul_motr_proc_status", str),
    ],
)

MotrProcStatusLocalRemote = NamedTuple(
    'MotrProcStatusLocalRemote', [
        ('motr_proc_status_local', ObjHealth),
        ('motr_proc_status_remote', ObjHealth),
    ],
)

ObjStatus = NamedTuple("ObjStatus", [("resource_type", ObjT), ("status", str)])


def dump_json(obj) -> str:
    """
    Interface wrapper to automatically apply correct parameters for json
    serialization obj.
    """
    return simplejson.dumps(obj, for_json=True)


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


def get_process_base_fid(proc_fid: Fid) -> Fid:
    fid_mask: Fid = ObjTMaskMap[ObjT.PROCESS]
    base_fid = Fid(proc_fid.container,
                   (proc_fid.key & fid_mask.key))
    return base_fid


def get_process_keys(node_items: List[Any], fidk: int) -> List[Any]:
    fid = mk_fid(ObjT.PROCESS, fidk)
    return [
        x['Key'] for x in node_items
        if f'{fid}' == x['Key'].split('/')[-1]
    ]


def get_service_keys(node_items: List[Any], fidk: int) -> List[Any]:
    fid = mk_fid(ObjT.SERVICE, fidk)
    LOG.debug('fid: %s, fidk: %d', fid, fidk)
    return [
        x['Key'] for x in node_items
        if f'{fid}' == x['Key'].split('/')[-1]
    ]


def get_motr_processes_status():
    with motr_processes_lock:
        LOG.debug('Current motr_processes_status: %s',
                  motr_processes_status)
        return motr_processes_status


# bAdd indicate whether new entry should be added or status should be
# updated only if fid is already present
def set_motr_processes_status(fid, status, bAdd=False):
    with motr_processes_lock:
        if fid in motr_processes_status or bAdd:
            motr_processes_status[fid] = status
        LOG.debug('Updated motr_processes_status: %s',
                  motr_processes_status)


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


class ProcessGroup:
    def __init__(self, buckets_count: int):
        self.buckets: int = buckets_count
        self.process_locks = []
        for _ in range(self.buckets):
            self.process_locks.append(Lock())

    def process_group_lock(self, proc_fid: Fid):
        group = proc_fid.key % self.buckets
        self.process_locks[group].acquire()

    def process_group_unlock(self, proc_fid: Fid):
        group = proc_fid.key % self.buckets
        self.process_locks[group].release()
