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

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from threading import Event

from hax.exception import HAConsistencyException
from hax.types import (ByteCountStats, ConfHaProcess, Fid, FsStatsWithTime,
                       ObjT, ObjHealth, Profile, PverInfo,
                       m0HaProcessEvent, m0HaProcessType,
                       HaNoteStruct, m0HaObjState)
from hax.util import (repeat_if_fails, mk_fid, ServiceData,
                      get_motr_processes_status,
                      FidWithType, create_service_fid,
                      create_process_fid, PutKV,
                      ha_process_events, MotrConsulProcInfo,
                      wait_for_event)
from hax.consul.cache import uses_consul_cache

LOG = logging.getLogger('hax')


class ConfigManager(ABC):
    # Interface to be implemented by subclasses

    @abstractmethod
    def _service_by_name(self, hostname: str,
                         svc_name: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def _service_data(self, kv_cache=None) -> ServiceData:
        raise NotImplementedError

    @abstractmethod
    def get_all_nodes(self, kv_cache=None):
        raise NotImplementedError

    @abstractmethod
    def get_local_nodename(self) -> str:
        """
        Returns the logical name of the current node. This is the name that
        the ConfigManager is aware of. In other words, whenever the
        ConfigManager references a node, it will use the names that this
        function can return.
        """
        raise NotImplementedError

    @abstractmethod
    def is_node_alive(self, node: str, kv_cache=None) -> bool:
        """
        Checks whether the given node is alive.
        """
        raise NotImplementedError

    @abstractmethod
    def get_hax_ssl_config(self, kv_cache=None) -> Optional[Dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    def get_m0d_statuses(self,
                         motr_services=None,
                         kv_cache=None
                         ) -> List[Tuple[ServiceData, ObjHealth]]:
        """
        Return the list of all Motr service statuses according to
        ConfigManager. The following services are
        considered [default]: ios, confd.
        """
        raise NotImplementedError

    @abstractmethod
    def get_conf_obj_status(self,
                            obj_t: ObjT,
                            fidk: int,
                            kv_cache=None) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_service_data_by_name(self, name: str) -> List[ServiceData]:
        raise NotImplementedError

    @abstractmethod
    def get_services_by_parent_process(self,
                                       process_fid: Fid,
                                       kv_cache=None) -> List[FidWithType]:
        raise NotImplementedError

    @abstractmethod
    def get_disks_by_parent_process(self,
                                    process_fid: Fid,
                                    svc_fid: Fid) -> List[Fid]:
        raise NotImplementedError

    @abstractmethod
    def get_rm_fid(self, kv_cache=None) -> Fid:
        raise NotImplementedError

    @abstractmethod
    def get_node_fid(self, node: str, kv_cache=None) -> Optional[Fid]:
        """
        Returns the fid of the given node.

        Parameters:
            node : hostname of the node.
        """
        raise NotImplementedError

    @abstractmethod
    def get_node_name_by_fid(self,
                             node_fid: Fid,
                             kv_cache=None) -> Optional[str]:
        """
        Returns the node name by its FID value or None if the given FID doesn't
        correspond to any node.
        """
        raise NotImplementedError

    @abstractmethod
    def get_node_name_by_machineid(self,
                                   machineid: str,
                                   kv_cache=None,
                                   allow_null=False) -> Optional[str]:
        """
        Returns the node name by its machine id value or None if the given
        machine id doesn't correspond to any node.
        """
        raise NotImplementedError

    @abstractmethod
    def get_machineid_by_nodename(self,
                                  nodename: str,
                                  kv_cache=None,
                                  allow_null=False):
        """
        Returns the machine id by its node-name value or None if the given
        node-name doesn't correspond to any node.
        """
        raise NotImplementedError

    @abstractmethod
    def get_node_ctrl_fids(self,
                           node: str,
                           kv_cache=None) -> Optional[List[Fid]]:
        """
        Parameters:
            node : hostname of the node.
        """
        raise NotImplementedError

    @abstractmethod
    def get_io_service_devices(self,
                               ioservice_fid: Fid,
                               kv_cache=None) -> Optional[List[str]]:
        raise NotImplementedError

    @abstractmethod
    def get_device_controller(self, sdev_fid, kv_cache=None):
        raise NotImplementedError

    @abstractmethod
    def get_node_encl_fid(self, node: str, kv_cache=None) -> Optional[Fid]:
        """
        Returns the fid of the enclosure for the given node.

        Parameters:
            node : hostname of the node.
        """
        raise NotImplementedError

    @abstractmethod
    def all_io_services_failed(self, node: str, kv_cache=None) -> bool:
        """
        Checks if all the IO services of given node are in failed state.

        Parameters:
            node : hostname of the node.
        """
        raise NotImplementedError

    @abstractmethod
    def set_node_state(self,
                       node_fid: Fid,
                       status: ObjHealth,
                       kv_cache=None) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_encl_state(self,
                       encl_fid: Fid,
                       status: ObjHealth,
                       kv_cache=None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_ctrl_state_updates(self,
                               ctrl_fid: Fid,
                               status: ObjHealth,
                               kv_cache=None) -> List[PutKV]:
        raise NotImplementedError

    @abstractmethod
    def get_ctrl_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_encl_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_node_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_proc_restart_count(self, proc_fid: Fid) -> int:
        raise NotImplementedError

    @abstractmethod
    def set_proc_restart_count(self, proc_fid: Fid, count: int):
        raise NotImplementedError

    @abstractmethod
    def update_fs_stats(self, stats_data: FsStatsWithTime) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_pver_bc(self, data: ByteCountStats) -> None:
        """
        Updates bytecount stats per pool versions for all pvers
        under the ios service in consul kv.
        """
        raise NotImplementedError

    @abstractmethod
    def update_bc_for_dg_category(self,
                                  pver_bc: Dict[str, int],
                                  pver_state: Dict[str, PverInfo]):
        '''
        This function will update bytecount for subsequent dg state/category
        which will reflect on cluster status.
        '''
        raise NotImplementedError

    @abstractmethod
    def update_process_status(self, event: ConfHaProcess) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_drive_state(self,
                           drive_fids: List[Fid],
                           status: ObjHealth,
                           device_event=True,
                           kv_cache=None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_sdev_state_update(self,
                              sdev_fid: Fid,
                              state: str,
                              device_event=True,
                              kv_cache=None) -> List[PutKV]:
        raise NotImplementedError

    @abstractmethod
    def get_sdev_state(self, obj_t: ObjT, fidk: int, kv_cache=None) -> int:
        raise NotImplementedError

    @abstractmethod
    def drive_to_sdev_fid(self, drive_fid: Fid, kv_cache=None) -> Fid:
        raise NotImplementedError

    @abstractmethod
    def sdev_to_drive_fid(self, sdev_fid: Fid):
        raise NotImplementedError

    @abstractmethod
    def node_to_drive_fid(self, node_name: str, drive: str):
        raise NotImplementedError

    @abstractmethod
    def get_process_status(self,
                           fid: Fid,
                           proc_node=None,
                           kv_cache=None) -> MotrConsulProcInfo:
        raise NotImplementedError

    @abstractmethod
    def get_process_status_local(self,
                                 fid: Fid,
                                 proc_node=None,
                                 kv_cache=None) -> MotrConsulProcInfo:
        raise NotImplementedError

    @abstractmethod
    def get_process_full_fid(self, proc_base_fid: Fid) -> Optional[Fid]:
        raise NotImplementedError

    @abstractmethod
    def update_process_status_local(self, event: ConfHaProcess) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_service_health(self,
                           node: str,
                           svc_id: int,
                           kv_cache=None) -> ObjHealth:
        """
        Returns current status of a service identified by the given
        svc_id for a given node.
        """
        raise NotImplementedError

    @abstractmethod
    def get_process_node(self, proc_fid: Fid, kv_cache=None) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_encl_node(self, encl: Fid, kv_cache=None) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_ctrl_encl(self, ctrl: Fid, kv_cache=None) -> Fid:
        raise NotImplementedError

    @abstractmethod
    def get_ctrl_node(self, ctrl: Fid, kv_cache=None) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_service_process_fid(self, svc_fid: Fid, kv_cache=None) -> Fid:
        raise NotImplementedError

    @abstractmethod
    def get_profiles(self, kv_cache=None) -> List[Profile]:
        raise NotImplementedError

    @abstractmethod
    def get_process_based_node_state(self, node_fid: Fid) -> str:
        raise NotImplementedError

    @abstractmethod
    def set_process_state(self,
                          process_fid: Fid,
                          state: ObjHealth) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_configpath(self, allow_null=False):
        raise NotImplementedError

    @abstractmethod
    def init_motr_processes_status(self):
        raise NotImplementedError

    @abstractmethod
    def alloc_next_process_fid(self, process_fid: Fid) -> Fid:
        raise NotImplementedError

    @abstractmethod
    def get_node_health_status(self, node: str, kv_cache=None) -> str:
        """
        Returns the node health status string returned by Consul.
        Possible return values: passing, warning, critical
        """
        raise NotImplementedError

    @abstractmethod
    def get_node_hare_motr_s3_fids(self, node: str) -> List[Fid]:
        """
        Parameters:
            node : hostname of the node
        response:
            returns list of fids for hax, ioservices, confd and s3services
            configured and running on @node.
        """
        raise NotImplementedError

    @abstractmethod
    def is_proc_client(self, process_fid: Fid) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_leader_node(self) -> str:
        """
        Returns the node name of RC leader.
        Note: in case when RC leader is not elected yet, the node name may be
        just a randomly generated string (see hare-node-join script for
        more details).
        """
        raise NotImplementedError

    @abstractmethod
    def get_leader_session_no_wait(self) -> str:
        """
        Returns the RC leader session. HAConsistencyException is raised
        immediately if there is no RC leader selected at the moment.
        """
        raise NotImplementedError

    @abstractmethod
    def is_leader_value_present_for_session(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_session_node(self, session_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def destroy_session(self, session: str) -> None:
        """
        Destroys the given ConfigManager Session by name.
        The method doesn't raise any exception if the session doesn't exist.
        """
        raise NotImplementedError

    @abstractmethod
    def fid_to_endpoint(self, proc_fid: Fid) -> Optional[str]:
        raise NotImplementedError

    # Common functionality

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
    def get_leader_session(self) -> str:
        """
        Blocking version of `get_leader_session_no_wait()`.
        The method either returns the RC leader session or blocks until the
        session becomes available.
        """
        return str(self.get_leader_session_no_wait())

    def get_svc_status(self, srv_fid: Fid, kv_cache=None) -> str:
        try:
            return self.get_process_status(srv_fid,
                                           kv_cache=kv_cache).proc_status
        except Exception:
            return 'Unknown'

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

    @repeat_if_fails()
    def is_process_confd(self, proc_fid: Fid, kv_cache=None) -> bool:
        confds = self.get_confd_list()
        for confd in confds:
            if proc_fid == confd.fid:
                return True
        return False

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
        proc_status: ObjHealth = self.get_service_health(proc_node, pfid.key,
                                                         kv_cache=kv_cache)
        # Report ONLINE for hax and confd if they are already started.
        hax_fid = self.get_hax_fid(kv_cache=kv_cache)
        if (proc_status == ObjHealth.RECOVERING and
                (self.is_process_confd(pfid) or
                 pfid == hax_fid)):
            return HaNoteStruct.M0_NC_ONLINE
        return proc_status.to_ha_note_status()

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

    def get_device_ha_state(self, status: ObjHealth) -> str:

        device_ha_state_map = {
            ObjHealth.UNKNOWN: m0HaObjState.M0_NC_TRANSIENT,
            ObjHealth.RECOVERING: m0HaObjState.M0_NC_DTM_RECOVERING,
            ObjHealth.OK: m0HaObjState.M0_NC_ONLINE,
            ObjHealth.OFFLINE: m0HaObjState.M0_NC_TRANSIENT,
            ObjHealth.FAILED: m0HaObjState.M0_NC_FAILED,
            ObjHealth.REPAIR: m0HaObjState.M0_NC_REPAIR,
            ObjHealth.REPAIRED: m0HaObjState.M0_NC_REPAIRED,
            ObjHealth.REBALANCE: m0HaObjState.M0_NC_REBALANCE
            }
        return device_ha_state_map[status].name

    def is_proc_local(self, pfid: Fid) -> bool:
        local_node = self.get_local_nodename()
        proc_node = self.get_process_node(pfid)
        return bool(proc_node == local_node)

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

    def am_i_rc(self):
        # The call is already marked with @repeat_if_fails
        leader = self.get_leader_node()
        # The call doesn't communicate via Consul REST API
        this_node = self.get_local_nodename()
        return leader == this_node

    def get_local_node_status(self):
        total_processes = 0
        started_processes = 0
        for item in get_motr_processes_status().values():
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
