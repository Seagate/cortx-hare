# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
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
from typing import Any, Dict, List, Optional, Tuple
from time import sleep
from urllib3.exceptions import HTTPError

import simplejson
from consul import Consul, ConsulException
from requests.exceptions import RequestException

import util
from hax.log import TRACE
from hax.exception import HAConsistencyException
from hax.types import (ByteCountStats, ConfHaProcess, Fid, FsStatsWithTime,
                       ObjT, ObjHealth, ObjTMaskMap, Profile, PverInfo,
                       PverState, m0HaProcessEvent, m0HaProcessType,
                       KeyDelete, HaNoteStruct, m0HaObjState,
                       FidTypeToObjT)
from hax.util import (KVAdapter, CatalogAdapter, consul_to_local_nodename,
                      repeat_if_fails, mkServiceData, mk_fid, ServiceData,
                      set_motr_processes_status, ObjStatus, PutKV,
                      FidWithType, create_sdev_fid,
                      get_service_keys, create_process_fid,
                      ha_process_events, create_drive_fid,
                      MotrConsulProcInfo, get_process_base_fid,
                      ha_conf_obj_states, MotrConsulProcStatus,
                      MotrProcStatusLocalRemote, get_process_keys)
from hax.consul.cache import (uses_consul_cache, supports_consul_cache)

from .base import ConfigManager


LOG = logging.getLogger('hax')


class ConsulConfigManager(ConfigManager):
    def __init__(self, raw_client: Optional[Consul] = None):
        self.cns: Consul = raw_client or Consul()
        self.kv = KVAdapter(cns=self.cns)
        self.catalog = CatalogAdapter(cns=self.cns)
        self.all_node_items: Dict[Any, Any] = {}

    @repeat_if_fails()
    def get_process_full_fid(self, proc_base_fid: Fid) -> Optional[Fid]:
        proc_fid = self.kv.kv_get(str(proc_base_fid), recurse=False)
        if proc_fid is not None:
            pfid: Fid = Fid.parse(json.loads(proc_fid['Value']))
            return pfid
        return proc_base_fid

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
        base_fid = get_process_base_fid(new_proc_fid)
        # Save base fid to actualy fid mapping in Consul.
        while not self.kv.kv_put(f'{base_fid}',
                                 json.dumps(str(new_proc_fid))):
            sleep(1)
        return new_proc_fid

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
    def _service_data(self, kv_cache=None) -> ServiceData:
        my_fidk = self.get_hax_fid(kv_cache=kv_cache).key
        services = self.catalog.get_services('hax')
        for svc in services:
            if int(svc['ServiceID']) == my_fidk:
                return mkServiceData(svc)
        raise RuntimeError('Unreachable')

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
    @repeat_if_fails()
    def get_hax_ssl_config(self, kv_cache=None) -> Optional[Dict[str, str]]:
        ssl_data = self.kv.kv_get('ssl/hax', kv_cache=kv_cache,
                                  allow_null=True)
        if not ssl_data:
            return None
        data: Optional[Dict[str, str]] = json.loads(ssl_data['Value'])
        return data

    @repeat_if_fails()
    def fid_to_endpoint(self, proc_fid: Fid) -> Optional[str]:
        pfidk = int(proc_fid.key)
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

    def get_all_nodes_cached(self):
        if not self.all_node_items:
            self.all_node_items = self.get_all_nodes()
        return self.all_node_items

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
            motr_services = set(['ios'])
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

    @uses_consul_cache
    def get_services_by_parent_process(self,
                                       process_fid: Fid,
                                       kv_cache=None) -> List[FidWithType]:
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
        node_items = self.get_all_nodes_cached()
        client_types = self.get_m0_client_types()
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
            if srv_type in client_types:
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
    @uses_consul_cache
    def get_conf_obj_status(self,
                            obj_t: ObjT,
                            fidk: int,
                            kv_cache=None) -> int:

        obj_state: int = HaNoteStruct.M0_NC_ONLINE
        if obj_t.name in (ObjT.PROCESS.name, ObjT.SERVICE.name):
            # 'node/<node_name>/process/<process_fidk>/service/type'
            node_items = self.get_all_nodes_cached()
            # TODO [KN] This code is too cryptic. To be refactored.
            func = getattr(util, "get_{}_keys".format(obj_t.name.lower()))
            keys = func(node_items, fidk)
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

        device_obj_types = {
            ObjT.SDEV.name: self.get_sdev_state,
            ObjT.DRIVE.name: self.get_sdev_state,
            ObjT.NODE.name: self.get_node_state,
            ObjT.ENCLOSURE.name: self.get_encl_state,
            ObjT.CONTROLLER.name: self.get_ctrl_state
        }
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
    def get_proc_node_health(self, proc_fid: Fid) -> ObjHealth:
        node = self.get_process_node(proc_fid)
        node_data = self.get_node_health_details(node)
        if not node_data:
            return ObjHealth.OFFLINE
        LOG.debug('node data: %s', node_data)
        node_status = str(node_data[0]['Status'])
        if node_status != 'passing':
            return ObjHealth.OFFLINE
        return ObjHealth.OK

    @repeat_if_fails()
    @uses_consul_cache
    def get_node_fid(self, node: str, kv_cache=None,
                     use_cache=True) -> Optional[Fid]:
        """
        Returns the fid of the given node.

        Parameters:
            node : hostname of the node.
        """
        # Example,
        # m0conf/nodes/
        # 0x6e00000000000001:0x3:{"name": "ssc-vm-1623.colo.seagate.com",
        #                         "state": "M0_NC_UNKNOWN"}
        if not use_cache:
            node_items = self.get_all_nodes(kv_cache=kv_cache)
        else:
            node_items = self.get_all_nodes_cached()
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

    @uses_consul_cache
    def get_machineid_by_nodename(self,
                                  nodename: str,
                                  kv_cache=None,
                                  allow_null=False):
        """
        Returns the machine id by its node-name value or None if the given
        node-name doesn't correspond to any node.
        """
        node_key = self.kv.kv_get(nodename, kv_cache=kv_cache,
                                  allow_null=allow_null)
        if node_key:
            machineid: bytes = node_key['Value']
            return machineid.decode('utf-8')
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
        sdev_items = self.get_all_nodes_cached()
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

    def ha_note_to_objhealth(self, state: int) -> ObjHealth:
        ha_note_to_objhealth = {
            HaNoteStruct.M0_NC_FAILED: ObjHealth.FAILED,
            HaNoteStruct.M0_NC_ONLINE: ObjHealth.OK,
            HaNoteStruct.M0_NC_TRANSIENT: ObjHealth.OFFLINE,
            HaNoteStruct.M0_NC_DTM_RECOVERING: ObjHealth.RECOVERING,
            HaNoteStruct.M0_NC_REPAIR: ObjHealth.REPAIR,
            HaNoteStruct.M0_NC_REPAIRED: ObjHealth.REPAIRED,
            HaNoteStruct.M0_NC_REBALANCE: ObjHealth.REBALANCE,
            HaNoteStruct.M0_NC_UNKNOWN: ObjHealth.UNKNOWN
        }
        return ha_note_to_objhealth[state]

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
        node_items = self.get_all_nodes_cached()
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
            LOG.debug('Node=%s state=%s', node_fid, state)
            return m0HaObjState.parse(state)
        return m0HaObjState.M0_NC_ONLINE

    @repeat_if_fails()
    def get_proc_restart_count(self, proc_fid: Fid) -> int:
        local_node = self.get_local_nodename()
        key = f'{local_node}/process_restarts/{proc_fid}'
        restart_count_val = self.kv.kv_get(key, allow_null=True,
                                           recurse=False)
        if restart_count_val:
            restart_count = json.loads(restart_count_val['Value'])
            return int(restart_count)
        return 0

    @repeat_if_fails()
    def set_proc_restart_count(self, proc_fid: Fid, count: int):
        local_node = self.get_local_nodename()
        key = f'{local_node}/process_restarts/{proc_fid}'
        self.kv.kv_put(key, json.dumps(str(count)))

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

        set_motr_processes_status(str(event.fid),
                                  ha_process_events[event.chp_event])

    @supports_consul_cache
    def update_drive_state(self,
                           drive_fids: List[Fid],
                           status: ObjHealth,
                           device_event=True,
                           kv_cache=None) -> None:
        device_state_map = {
            ObjHealth.OK: 'online',
            ObjHealth.UNKNOWN: 'offline',
            ObjHealth.RECOVERING: 'dtm_recovering',
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
            'dtm_recovering': HaNoteStruct.M0_NC_DTM_RECOVERING,
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
            if str(val['state']).lower() in ['unknown', 'm0_nc_unknown',
                                             'dtm_recovering']:
                return HaNoteStruct.M0_NC_ONLINE
            else:
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
        sdev_items = self.get_all_nodes_cached()
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
        proc_base_fid = self.get_base_fid(fid)
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
        proc_base_fid = self.get_base_fid(fid)
        this_node = self.get_local_nodename()
        key = f'{this_node}/processes/{proc_base_fid}'
        status = self.kv.kv_get(key, kv_cache=kv_cache, allow_null=True)
        if status:
            val = json.loads(status['Value'])
            return MotrConsulProcInfo(val['state'], val['type'])
        else:
            return MotrConsulProcInfo('Unknown', 'Unknown')

    @repeat_if_fails()
    def get_obj_full_fid(self, base_fid: Fid) -> Fid:
        full_fid = self.kv.kv_get(str(base_fid), allow_null=True,
                                  recurse=False)
        if full_fid is not None:
            fid: Fid = Fid.parse(json.loads(full_fid['Value']))
            return fid
        return base_fid

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
        node_items = self.get_all_nodes_cached()
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
                                    ObjHealth.OFFLINE),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STARTED'):
            local_remote_health_ret(ObjHealth.RECOVERING,
                                    ObjHealth.RECOVERING),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_DTM_RECOVERED'):
            local_remote_health_ret(ObjHealth.OK,
                                    ObjHealth.OK),
            cur_consul_status('passing', 'M0_CONF_HA_PROCESS_STOPPED'):
            local_remote_health_ret(ObjHealth.UNKNOWN,
                                    ObjHealth.UNKNOWN),
            cur_consul_status('passing', 'Unknown'):
            local_remote_health_ret(ObjHealth.UNKNOWN,
                                    ObjHealth.UNKNOWN),
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
            LOG.debug('node data: %s', node_data)
            node_status = str(node_data[0]['Status'])
            if node_status != 'passing':
                return ObjHealth.OFFLINE
            status = ObjHealth.UNKNOWN
            for item in node_data:
                if item['ServiceID'] == str(svc_id):
                    pfid = create_process_fid(svc_id)
                    LOG.debug('item.status %s svc id: %s',
                              item['Status'], str(svc_id))
                    if item['Status'] in ('critical', 'warning'):
                        return ObjHealth.OFFLINE
                    cns_status = self.get_process_status(pfid,
                                                         kv_cache=kv_cache)
                    svc_health = svc_to_motr_status_map[
                        MotrConsulProcStatus(
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
            proc_base_fid = self.get_base_fid(proc_fid)
            fidk = proc_base_fid.key
            # 'node/<node_name>/process/<process_fidk>/service/type'
            # node_items = self.kv.kv_get('m0conf/nodes',
            #                             recurse=True,
            #                             kv_cache=kv_cache)
            node_items = self.get_all_nodes_cached()
            LOG.log(TRACE, 'node items: %s', node_items)
            if ObjT.PROCESS.value == proc_base_fid.container:
                keys = get_process_keys(node_items, fidk)
            elif ObjT.SERVICE.value == proc_base_fid.container:
                keys = get_service_keys(node_items, fidk)
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
        node_items = self.get_all_nodes_cached()
        keys = get_service_keys(node_items, svc_fid.key)
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
    def get_process_based_node_state(self, node_fid: Fid) -> str:

        proc_keys = self.kv.kv_get('processes', recurse=True)
        all_procs = {}
        for proc in proc_keys:
            fid = proc['Key'].split('/')[1]
            state = json.loads(proc['Value'])['state']
            all_procs[fid] = state

        node_procs = self.kv.kv_get(f'm0conf/nodes/{node_fid}/processes',
                                    recurse=True)
        total_processes = 0
        started_processes = 0
        for item in node_procs:
            # m0conf/nodes/0x6e00000000000001:0x3/processes/
            # 0x7200000000000001:0xa:
            # {"name": "m0_server", "state": "online"}
            regex = re.compile('^m0conf\\/.*\\/processes\\/([^/]+)$')
            match_result = re.match(regex, item['Key'])
            if not match_result:
                continue
            p_fid = match_result.group(1)
            # Counting total number of configured processes
            total_processes += 1
            # if process is not found then it is considered as offline
            if p_fid not in all_procs:
                continue
            # Checking if status is M0_CONF_HA_PROCESS_STARTED
            if all_procs[p_fid] in (
                    m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED.name,
                    m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED.name):
                started_processes += 1
        LOG.debug('total procs=%s, started procs=%s', total_processes,
                  started_processes)
        fin_state = 'degraded'
        if total_processes == started_processes:
            fin_state = 'online'
        elif started_processes == 0:
            fin_state = 'offline'
        return fin_state

    def objHealthToProcessEvent(self, health: ObjHealth):
        healthToProcessEvent: dict = {
            ObjHealth.RECOVERING: m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED,
            ObjHealth.OK: m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED,
            ObjHealth.FAILED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ObjHealth.OFFLINE: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ObjHealth.UNKNOWN: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED,
            ObjHealth.STOPPED: m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED
        }
        return healthToProcessEvent[health]

    def processEventToObjHealth(self, proc_type: m0HaProcessType,
                                proc_event: m0HaProcessEvent) -> ObjHealth:
        motr_to_svc_status = {
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED): (
                    ObjHealth.OK),
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0MKFS,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED): (
                    ObjHealth.FAILED),
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0D,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED): (
                    ObjHealth.RECOVERING),
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0D,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED): (
                    ObjHealth.OK),
            (m0HaProcessType.M0_CONF_HA_PROCESS_M0D,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED): (
                    ObjHealth.FAILED),
            (m0HaProcessType.M0_CONF_HA_PROCESS_OTHER,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STARTED): (
                    ObjHealth.RECOVERING),
            (m0HaProcessType.M0_CONF_HA_PROCESS_OTHER,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_DTM_RECOVERED): (
                    ObjHealth.OK),
            (m0HaProcessType.M0_CONF_HA_PROCESS_OTHER,
                m0HaProcessEvent.M0_CONF_HA_PROCESS_STOPPED): (
                    ObjHealth.FAILED)}
        LOG.debug('chp_type=%d chp_event=%d',
                  proc_type, proc_event)
        return motr_to_svc_status[(proc_type, proc_event)]

    @repeat_if_fails()
    def set_process_state(self,
                          process_fid: Fid,
                          state: ObjHealth) -> None:
        LOG.info('Setting process=%s in KV with state=%s',
                 process_fid, state)
        process_state_map = {
            ObjHealth.OK: 'online',
            ObjHealth.FAILED: 'failed',
            ObjHealth.OFFLINE: 'offline',
            ObjHealth.UNKNOWN: 'unknown',
            ObjHealth.STOPPED: 'stopped',
            ObjHealth.RECOVERING: 'dtm_recovering'
        }
        proc_base_fid = self.get_base_fid(process_fid)

        # Example key is as follows
        # m0conf/nodes/0x6e00000000000001:0x3/processes/0x7200000000000001:
        # 0x15:{"name": "m0_server", "state": "M0_NC_UNKNOWN"}
        node_items = self.get_all_nodes_cached()
        regex = re.compile(
            f'^m0conf\\/nodes\\/.*\\/processes\\/{proc_base_fid}$')
        for item in node_items:
            match_result = re.match(regex, item['Key'])
            if not match_result:
                continue
            value = json.loads(item['Value'])
            value['state'] = process_state_map[state]
            LOG.info('set_process_state: %s', json.dumps(value))
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
    def cleanup_process_restarts(self):
        local_node = self.get_local_nodename()
        keys: List[KeyDelete] = [
            KeyDelete(name=f'{local_node}/process_restarts/', recurse=True),
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

    @repeat_if_fails()
    def init_motr_processes_status(self):
        local_node = self.get_local_nodename()
        fid = self.get_node_fid(local_node, use_cache=False)
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
            set_motr_processes_status(str(p_fid),
                                      ha_process_events[3],
                                      True)

    @repeat_if_fails()
    def obj_dynamic_fidk_lock(self, objt: ObjT) -> bool:
        # Acquire lock to update last_updated_base_fidk.
        # This will block until lock is acquired.
        # Will break if any other exception than
        # HAConsistencyException occurs.
        hax_fid = self.get_hax_fid()
        value = json.dumps({'owner': hax_fid})
        try:
            while not self.kv.kv_put(
                          f'fidk_update_lock/{objt.name}',
                          value, cas=0):
                sleep(1)
            return True
        except Exception:
            return False

    @repeat_if_fails()
    def obj_dynamic_fidk_unlock(self, objt: ObjT):
        # Release fidk_update_lock.
        # This will block until released.
        try:
            keys: List[KeyDelete] = [
                KeyDelete(name=f'fidk_update_lock/{objt.name}',
                          recurse=True),
            ]
            while not self.kv.kv_delete_in_transaction(keys):
                sleep(1)
        except Exception:
            raise RuntimeError('Unreachable')

    @repeat_if_fails()
    def revoke_all_dynamic_fidk_lock_for(self, hax_fid: Fid):
        try:
            fidk_lock_items = self.kv.kv_get('fidk_update_lock',
                                             allow_null=True,
                                             recurse=True)
            keys_to_del: List[KeyDelete] = []
            for item in fidk_lock_items:
                owner_data = json.loads(item['Value'])
                owner_fid = Fid.parse(owner_data['owner'])
                if owner_fid == hax_fid:
                    keys_to_del.append(KeyDelete(name=item['Key'],
                                       recurse=True))
            while not self.kv.kv_delete_in_transaction(keys_to_del):
                sleep(1)
        except Exception:
            raise RuntimeError('Unreachable')

    @repeat_if_fails()
    def get_obj_next_dynamic_fidk_lock(self, objt: ObjT) -> int:
        if self.obj_dynamic_fidk_lock(objt):
            fidk = self.kv.kv_get(f'last_dynamic_fid_key/{objt.name.lower()}',
                                  recurse=False)
            new_fidk = int(json.loads(fidk['Value'])) + 1
            # Update dynamic fid key.
            while not self.kv.kv_put(
                          f'last_dynamic_fid_key/{objt.name.lower()}',
                          json.dumps(str(new_fidk))):
                sleep(1)
            self.obj_dynamic_fidk_unlock(objt)
        return new_fidk

    @repeat_if_fails()
    def alloc_next_obj_fid(self, obj_fid: Fid) -> Fid:
        objt: ObjT = FidTypeToObjT[obj_fid.container]
        next_fidk = self.get_obj_next_dynamic_fidk_lock(objt)
        fid_mask: Fid = ObjTMaskMap[objt]
        fid_cont = obj_fid.container
        fid_key = obj_fid.key + ((fid_mask.key * next_fidk) + next_fidk)
        new_obj_fid = Fid(fid_cont, fid_key)
        base_fid = self.get_base_fid(new_obj_fid)
        # Save base fid to actualy fid mapping in Consul.
        while not self.kv.kv_put(f'{base_fid}',
                                 json.dumps(str(new_obj_fid))):
            sleep(1)
        return new_obj_fid

    def update_process_fid(self, proc_fid: Fid) -> List[Fid]:
        new_fids: List[Fid] = []
        # First allocate new process fid.
        new_fids.append(self.alloc_next_obj_fid(proc_fid))
        service_list = self.get_services_by_parent_process(proc_fid)
        for svc in service_list:
            new_fids.append(self.alloc_next_obj_fid(svc.fid))
        return new_fids

    def get_base_fid(self, obj_fid: Fid) -> Fid:
        objt: ObjT = FidTypeToObjT[obj_fid.container]
        fid_mask: Fid = ObjTMaskMap[objt]
        base_fid = Fid(obj_fid.container,
                       (obj_fid.key & fid_mask.key))
        return base_fid

    @repeat_if_fails()
    def get_m0_client_types(self) -> List[str]:
        m0_client_types = self.kv.kv_get('m0_client_types')
        client_types = []
        for client_type in json.loads(m0_client_types['Value']):
            client_types.append(client_type)
        return client_types
