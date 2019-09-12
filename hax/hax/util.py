import json

from consul import Consul

from hax.exception import HAConsistencyException
from hax.types import Fid

SERVICE_CONTAINER = 0x7300000000000001


class ConsulUtil:
    def __init__(self):
        self.cns = Consul()
        self.event_map = {
            0: "M0_CONF_HA_PROCESS_STARTING",
            1: "M0_CONF_HA_PROCESS_STARTED",
            2: "M0_CONF_HA_PROCESS_STOPPING",
            3: "M0_CONF_HA_PROCESS_STOPPED"
        }

    # Returns the fid of the current hax process (in other words, returns
    # "my" fid)
    def get_hax_fid(self):
        serv = self.get_local_service_by_name('hax')
        return Fid.parse(serv.get('ServiceID'))

    def get_ha_fid(self):
        serv = self.get_local_service_by_name('ha')
        return Fid.parse(serv.get('ServiceID'))

    def get_rm_fid(self):
        serv = self.get_local_service_by_name('rm')
        return Fid.parse(serv.get('ServiceID'))

    def get_my_nodename(self):
        return self.cns.agent.self().get('Config').get('NodeName')

    def get_local_service_by_name(self, name):
        hostname = self.get_my_nodename()

        service = self.cns.catalog.service(service=name)[1]
        srv = list(filter(lambda x: x.get('Node') == hostname, service))
        if not len(srv):
            raise HAConsistencyException(
                f'No {name} service found in Consul at Node={hostname}')
        return srv[0]

    def get_hax_endpoint(self):
        my_fid = self.get_hax_fid()
        services = self.cns.catalog.service(service='hax')[1]
        data = list(
            map(self._to_canonical_service_data,
                filter(lambda x: Fid.parse(x.get('ServiceID')) == my_fid,
                       services)))
        return data[0].get('address')

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
        node = service.get('Node')
        fid = service.get('ServiceID')
        srv_address = service.get('ServiceAddress')
        srv_port = service.get('ServicePort')
        return {
            'node': node,
            'fid': Fid.parse(fid),
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
