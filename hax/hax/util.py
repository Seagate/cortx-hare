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
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
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
                       m0HaProcessType)

__all__ = ['ConsulUtil', 'create_process_fid', 'create_service_fid',
           'create_sdev_fid', 'create_drive_fid']

LOG = logging.getLogger('hax')

# XXX What is the difference between `ip_addr` and `address`?
# The names are hard to discern.
ServiceData = NamedTuple('ServiceData', [('node', str), ('fid', Fid),
                                         ('ip_addr', str), ('address', str)])

FidWithType = NamedTuple('FidWithType', [('fid', Fid), ('service_type', str)])


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


class ConsulKVBasic:
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


class ConsulUtil:
    def __init__(self, raw_client: Optional[Consul] = None):
        self.cns: Consul = raw_client or Consul()
        self.kv = ConsulKVBasic(cns=self.cns)

    def _catalog_service_names(self) -> List[str]:
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

    def _catalog_service_get(self, svc_name: str) -> List[Dict[str, Any]]:
        try:
            return self.cns.catalog.service(service=svc_name)[1]
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                'Could not access Consul Catalog') from e

    def _service_by_name(self, hostname: str, svc_name: str) -> Dict[str, Any]:
        for svc in self._catalog_service_get(svc_name):
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
        services = self._catalog_service_get('hax')
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

    def get_session_node(self, session_id: str) -> str:
        try:
            session = self.cns.session.info(session_id)[1]
            return str(session['Node'])  # principal RM
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate to'
                                         ' Consul Agent') from e

    def get_svc_status(self, srv_fid: Fid) -> str:
        try:
            key = f'processes/{srv_fid}'
            raw_data = self.kv.kv_get(key)
            LOG.log(TRACE, 'Raw value from KV: %s', raw_data)
            data = raw_data['Value']
            value: str = json.loads(data)['state']
            return value
        except Exception:
            return 'Unknown'

    def get_m0d_statuses(self) -> List[Tuple[ServiceData, str]]:
        """
        Return the list of all Motr service statuses according to Consul
        watchers. The following services are considered: ios, confd.
        """
        m0d_services = set(['ios', 'confd'])
        result = []
        for service_name in self._catalog_service_names():
            if service_name not in m0d_services:
                continue
            data = self.get_service_data_by_name(service_name)
            result += [(item, self.get_svc_status(item.fid)) for item in data]
        return result

    def get_service_data_by_name(self, name: str) -> List[ServiceData]:
        services = self._catalog_service_get(name)
        LOG.log(TRACE, 'Services "%s" received: %s', name, services)
        return list(map(mkServiceData, services))

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
            f'{svc_fid}\\/(.+)$')
        disks = []
        for node in node_items:
            match_result = re.match(regex, node['Key'])
            if not match_result:
                continue
            sdev_fid_item = node['Key'].split('/')[8]
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

    def get_conf_obj_status(self, obj_t: ObjT, fidk: int) -> str:
        # 'node/<node_name>/process/<process_fidk>/service/type'
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        # TODO [KN] This code is too cryptic. To be refactored.
        keys = getattr(self,
                       'get_{}_keys'.format(obj_t.name.lower()))(node_items,
                                                                 fidk)
        assert len(keys) == 1
        key = keys[0].split('/')
        node_key = ('/'.join(key[:3]))
        node_val = self.kv.kv_get(node_key)
        data = node_val['Value']
        node_name: str = json.loads(data)['name']
        return self.get_node_health(node_name)

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

    def get_node_health(self, node: str) -> str:
        try:
            node_data = self.cns.health.node(node)[1]
            if not node_data:
                return 'failed'
            return str(node_data[0]['Status'])
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException(
                f'Failed to get {node} node health') from e

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

    def update_process_status(self, event: ConfHaProcess) -> None:
        assert 0 <= event.chp_event < len(ha_process_events), \
            f'Invalid event type: {event.chp_event}'

        data = json.dumps({'state': ha_process_events[event.chp_event]})
        key = f'processes/{event.fid}'
        LOG.debug('Setting process status in KV: %s:%s', key, data)
        self.kv.kv_put(key, data)

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

    def get_process_status(self, fid: Fid) -> str:
        key = f'processes/{fid}'
        status = self.kv.kv_get(key)
        return str(json.loads(status['Value'])['state'])

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

    @repeat_if_fails()
    def get_service_health(self, node: str, svc_id: int) -> ServiceHealth:
        """
        Returns current status of a Consul service identified by the given
        svc_id for a given node.
        """
        try:
            node_data: List[Dict[str, Any]] = self.cns.health.node(node)[1]
            if not node_data:
                return ServiceHealth.FAILED
            node_status = str(node_data[0]['Status'])
            if node_status != 'passing':
                return ServiceHealth.FAILED
            status = ServiceHealth.UNKNOWN
            for item in node_data:
                if item['ServiceID'] == str(svc_id):
                    LOG.debug('item.status %s', item['Status'])
                    if item['Status'] == 'passing':
                        status = ServiceHealth.OK
                    elif item['Status'] == 'warning':
                        fid = create_process_fid(svc_id)
                        svc_consul_status = self.get_svc_status(fid)
                        if (svc_consul_status in
                            ('M0_CONF_HA_PROCESS_STARTING',
                             'M0_CONF_HA_PROCESS_STARTED')):
                            # We are returning unknown status for the service
                            # as we cannot confirm the actual status of the
                            # service from the available data. The node status
                            # is 'passing' but service status is 'warning' and
                            # the service status in Consul is either
                            # M0_CONF_HA_PROCESS_STARTING or
                            # M0_CONF_HA_PROCESS_STARTED. So we are not sure
                            # because it is possible that the service has
                            # failed but consul status is not yet updated yet.
                            # So we return unknown now, the caller can re try
                            # after sometime and once all the 3 status are
                            # either passing or atleast the node status itself
                            # is failed, we will return OK or FAILED
                            # accordingly.
                            status = ServiceHealth.UNKNOWN
                        elif (svc_consul_status in
                                ('M0_CONF_HA_PROCESS_STOPPED',
                                 'M0_CONF_HA_PROCESS_STOPPING')):
                            status = ServiceHealth.OFFLINE
                        else:
                            status = ServiceHealth.FAILED
                    else:
                        status = ServiceHealth.FAILED

                    return status
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate '
                                         'to Consul Agent') from e
        return status

    def get_process_node(self, proc_fid: Fid) -> str:
        fidk = proc_fid.key
        # 'node/<node_name>/process/<process_fidk>/service/type'
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        keys = self.get_process_keys(node_items, fidk)
        assert len(keys) == 1
        key = keys[0].split('/')
        node_key = ('/'.join(key[:3]))
        node_val = self.kv.kv_get(node_key)
        data = node_val['Value']
        return str(json.loads(data)['name'])

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
        started = ['M0_CONF_HA_PROCESS_STARTED' == v[1] for v in statuses]
        return started

    @repeat_if_fails()
    def ensure_motr_all_started(self, event: Event):
        while True:
            started = self.ensure_ioservices_running()
            if all(started):
                LOG.debug('According to Consul all confds have been started')
                return
            wait_for_event(event, 5)

    def get_process_current_status(self, status_reported: ServiceHealth,
                                   proc_fid: Fid) -> ServiceHealth:
        status_current = status_reported
        # Reconfirm the process status only if the reported status is FAILED.
        if status_reported == ServiceHealth.FAILED:
            # check one more time before broadcasting failure.
            node = self.get_process_node(proc_fid)
            status_current = self.get_service_health(node,
                                                     proc_fid.key)
            LOG.info('node: %s proc: %s current status: %s',
                     node, proc_fid, status_current)
        return status_current

    def service_health_to_m0dstatus_update(self, proc_fid: Fid,
                                           svc_health: ServiceHealth):
        svcHealthToM0status: dict = {
            ServiceHealth.OK: m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED,
            ServiceHealth.FAILED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ServiceHealth.UNKNOWN: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED
        }
        ev = ConfHaProcess(chp_event=svcHealthToM0status[svc_health],
                           chp_type=m0HaProcessType.M0_CONF_HA_PROCESS_M0D,
                           chp_pid=0,
                           fid=proc_fid)
        self.update_process_status(ev)


def dump_json(obj) -> str:
    """
    Interface wrapper to automatically apply correct parameters for json
    serialization obj.
    """
    return simplejson.dumps(obj, for_json=True)
