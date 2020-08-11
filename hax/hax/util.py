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
from functools import wraps
from time import sleep
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import simplejson
from consul import Consul, ConsulException
from requests.exceptions import RequestException
from urllib3.exceptions import HTTPError

from hax.exception import HAConsistencyException
from hax.types import ConfHaProcess, Fid, FsStatsWithTime, ObjT

__all__ = ['ConsulUtil', 'create_process_fid']

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


# See enum m0_conf_ha_process_event in Motr source code.
ha_process_events = ('M0_CONF_HA_PROCESS_STARTING',
                     'M0_CONF_HA_PROCESS_STARTED',
                     'M0_CONF_HA_PROCESS_STOPPING',
                     'M0_CONF_HA_PROCESS_STOPPED')


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
                    logging.debug(
                        'Attempting to invoke the repeatable call: %s',
                        f.__name__)
                    result = f(*args, **kwds)
                    logging.debug('The repeatable call succeeded: %s',
                                  f.__name__)
                    return result
                except HAConsistencyException as e:
                    attempt_count += 1
                    if max_retries >= 0 and attempt_count > max_retries:
                        logging.warn(
                            'Too many errors happened in a row '
                            '(max_retries = %d)', max_retries)
                        raise e
                    logging.warn(
                        f'Got HAConsistencyException: {e.message} '
                        f'(attempt {attempt_count}). The'
                        f' attempt will be repeated in {wait_seconds} seconds')
                    sleep(wait_seconds)

        return wrapper

    return callable


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


class ConsulUtil:
    def __init__(self):
        self.cns: Consul = Consul()
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

    def _local_service_by_name(self, name: str) -> Dict[str, Any]:
        """
        Returns the service data by its name assuming that it runs at the same
        node to the current hax process.
        """
        try:
            local_nodename = os.environ.get('HARE_HAX_NODE_NAME') or \
                self.cns.agent.self()['Config']['NodeName']
        except (ConsulException, HTTPError, RequestException) as e:
            raise HAConsistencyException('Failed to communicate '
                                         'to Consul Agent') from e
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
        except ConsulException as e:
            raise HAConsistencyException('Failed to communicate to'
                                         ' Consul Agent') from e

    def get_m0d_statuses(self) -> List[Tuple[ServiceData, str]]:
        """
        Return the list of all Motr service statuses according to Consul
        watchers. The following services are considered: ios, confd.
        """
        def get_status(srv: ServiceData) -> str:
            try:
                key = f'processes/{srv.fid}'
                raw_data = self.kv.kv_get(key)
                logging.debug('Raw value from KV: %s', raw_data)
                data = raw_data['Value']
                value: str = json.loads(data)['state']
                return value
            except Exception:
                return 'Unknown'

        m0d_services = set(['ios', 'confd'])
        result = []
        for service_name in self._catalog_service_names():
            if service_name not in m0d_services:
                continue
            data = self.get_service_data_by_name(service_name)
            result += [(item, get_status(item)) for item in data]
        return result

    def get_service_data_by_name(self, name: str) -> List[ServiceData]:
        services = self._catalog_service_get(name)
        logging.debug('Services "%s" received: %s', name, services)
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

    def get_conf_obj_status(self, obj_t: ObjT, fidk: int) -> str:
        # 'node/<node_name>/process/<process_fidk>/service/type'
        node_items = self.kv.kv_get('m0conf/nodes', recurse=True)
        # TODO [KN] This code is too cryptic. To be refactored.
        keys = getattr(self,
                       'get_{}_keys'.format(obj_t.name.lower()))(node_items,
                                                                 fidk)
        assert keys
        node_name = keys[0].split('/', 3)[2]
        return self.get_node_health(node_name)

    @staticmethod
    def get_process_keys(node_items: List[Any], fidk: int) -> List[Any]:
        return [
            x['Key'] for x in node_items
            if '/processes/' in x['Key'] and str(fidk) in x['Key']
        ]

    @staticmethod
    def get_service_keys(node_items: List[Any], fidk: int) -> List[Any]:
        return [
            x['Key'] for x in node_items
            if '/services/' in x['Key'] and int(x['Value']) == fidk
        ]

    def get_node_health(self, node: str) -> str:
        try:
            node_data = self.cns.health.node(node)[1]
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
        logging.debug('Setting process status in KV: %s:%s', key, data)
        self.kv.kv_put(key, data)
