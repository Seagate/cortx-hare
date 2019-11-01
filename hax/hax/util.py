import os
import json
from typing import Any, Dict, NamedTuple

from consul import Consul

from hax.exception import HAConsistencyException
from hax.types import Fid

SERVICE_CONTAINER = 0x7300000000000001
PROCESS_CONTAINER = 0x7200000000000001
ServiceData = NamedTuple('ServiceData', [('node', str), ('fid', Fid),
                                         ('ip_addr', str),
                                         ('address', str)])


def create_process_fid(key: int) -> Fid:
    """
    Returns a correct Fid instance by the given fidk value. The resulting
    Fid will correspond to a Mero process.
    """
    return Fid(PROCESS_CONTAINER, key)


def _to_service_fid(key: int) -> Fid:
    return Fid(SERVICE_CONTAINER, key)


class ConsulUtil:
    def __init__(self):
        self.cns: Consul = Consul()
        self.event_map = {
            0: "M0_CONF_HA_PROCESS_STARTING",
            1: "M0_CONF_HA_PROCESS_STARTED",
            2: "M0_CONF_HA_PROCESS_STOPPING",
            3: "M0_CONF_HA_PROCESS_STOPPED"
        }

    def get_hax_fid(self) -> Fid:
        """
        Returns the fid of the current hax process (in other words, returns
        "my own" fid)
        """
        serv: Dict[str, Any] = self.get_local_service_by_name('hax')
        return create_process_fid(int(serv['ServiceID']))

    def get_ha_fid(self) -> Fid:
        serv = self.get_local_service_by_name('hax')
        fidk = int(serv['ServiceID'])
        return _to_service_fid(fidk + 1)

    def get_rm_fid(self) -> Fid:
        lsess = self.get_leader_session()
        p_rm_node = self.get_session_node(lsess)
        serv = self.get_node_service_by_name(p_rm_node, 'confd')
        pfidk = int(serv['ServiceID'])
        key = f'node/{p_rm_node}/process/{pfidk}/service/rms'
        sfidk = self.cns.kv.get(key)[1]
        return _to_service_fid(int(sfidk['Value']))

    def get_my_nodename(self) -> str:
        return os.environ.get('HARE_HAX_NODE_NAME') or \
            self.cns.agent.self()['Config']['NodeName']

    def get_node_service_by_name(self, hostname, svc_name) -> Dict[str, Any]:
        for svc in self.cns.catalog.service(service=svc_name)[1]:
            if svc['Node'] == hostname:
                return svc
        raise HAConsistencyException(
            f'No {svc_name!r} Consul service found at node {hostname!r}')

    def get_local_service_by_name(self, name: str) -> Dict[str, Any]:
        """
        Returns the service data by its name assuming that it runs at the same
        node to the current hax process.
        """
        hostname = self.get_my_nodename()
        return self.get_node_service_by_name(hostname, name)

    def get_service_data(self) -> ServiceData:
        my_fid = self.get_hax_fid()
        services = self.cns.catalog.service(service='hax')[1]
        data = list(map(self._to_canonical_service_data,
                        filter(lambda x: int(x['ServiceID']) == my_fid.key,
                               services)))
        return data[0]

    def get_hax_endpoint(self) -> str:
        return self.get_service_data().address

    def get_hax_ip_address(self) -> str:
        return self.get_service_data().ip_addr

    def get_leader_session(self) -> str:
        leader = self.cns.kv.get('leader')[1]
        session = leader.get('Session')
        if not session:
            raise HAConsistencyException(
                'Could not get the leader from Consul')
        return str(session)

    def get_session_node(self, session_id: str) -> str:
        sess_details = self.cns.session.info(session_id)[1]
        return str(sess_details.get('Node'))  # principal RM

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

    def get_confd_list(self):
        services = self.cns.catalog.service(service='confd')[1]
        return list(map(self._to_canonical_service_data, services))

    def update_process_status(self, event):
        key = f'processes/{event.fid}'
        status_value = self.get_status_line(event.chp_event)
        self.cns.kv.put(key, status_value)

    def get_status_line(self, event_type):
        state_name = self.event_map[event_type]
        return json.dumps({'state': state_name})
