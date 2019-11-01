import os
import json

from consul import Consul

from hax.exception import HAConsistencyException
from hax.types import Fid

SERVICE_CONTAINER = 0x7300000000000001
PROCESS_CONTAINER = 0x7200000000000001


def create_process_fid(key):
    """
    Returns a correct Fid instance by the given fidk value. The resulting
    Fid will correspond to a Mero process.
    """
    return Fid(PROCESS_CONTAINER, int(key))


def _to_service_fid(key: int):
    return Fid(SERVICE_CONTAINER, int(key))


class ConsulUtil:
    def __init__(self):
        self.cns = Consul()
        self.event_map = {
            0: "M0_CONF_HA_PROCESS_STARTING",
            1: "M0_CONF_HA_PROCESS_STARTED",
            2: "M0_CONF_HA_PROCESS_STOPPING",
            3: "M0_CONF_HA_PROCESS_STOPPED"
        }

    def get_hax_fid(self):
        """
        Returns the fid of the current hax process (in other words, returns
        "my own" fid)
        """
        serv = self.get_local_service_by_name('hax')
        return create_process_fid(serv['ServiceID'])

    def get_ha_fid(self):
        serv = self.get_local_service_by_name('hax')
        fidk = int(serv['ServiceID'])
        return _to_service_fid(fidk + 1)

    def get_rm_fid(self):
        lsess = self.get_leader_session()
        p_rm_node = self.get_session_node(lsess)
        serv = self.get_node_service_by_name(p_rm_node, 'confd')
        pfidk = int(serv['ServiceID'])
        key = f'node/{p_rm_node}/process/{pfidk}/service/rms'
        sfidk = self.cns.kv.get(key)[1]
        return _to_service_fid(int(sfidk['Value']))

    def get_my_nodename(self):
        return (os.environ.get('HARE_HAX_NODE_NAME') or
                self.cns.agent.self()['Config']['NodeName'])

    def get_node_service_by_name(self, hostname, svc_name):
        for svc in self.cns.catalog.service(service=svc_name)[1]:
            if svc['Node'] == hostname:
                return svc
        raise HAConsistencyException(
            f'No {svc_name!r} Consul service found at node {hostname!r}')

    def get_local_service_by_name(self, name):
        """
        Returns the service data by its name assuming that it runs at the same
        node to the current hax process.
        """
        hostname = self.get_my_nodename()
        return self.get_node_service_by_name(hostname, name)

    def get_hax_endpoint(self):
        my_fid = self.get_hax_fid()
        services = self.cns.catalog.service(service='hax')[1]
        data = list(
            map(self._to_canonical_service_data,
                filter(lambda x: int(x['ServiceID']) == my_fid.key, services)))
        return data[0]['address']

    def get_leader_session(self):
        leader = self.cns.kv.get('leader')[1]
        session = leader.get('Session')
        if not session:
            raise HAConsistencyException(
                'Could not get the leader from Consul')
        return session

    def get_session_node(self, session_id):
        sess_details = self.cns.session.info(session_id)[1]
        return sess_details.get('Node')  # principal RM

    @staticmethod
    def _to_canonical_service_data(service):
        node = service['Node']
        fidk = service['ServiceID']
        srv_address = service['ServiceAddress']
        srv_port = service['ServicePort']
        return {
            'node': node,
            'fid': create_process_fid(fidk),
            'address': f'{srv_address}:{srv_port}'
        }

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
