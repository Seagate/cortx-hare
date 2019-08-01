import consul as c
from hax.types import Fid

SERVICE_CONTAINER = 0x7300000000000001


class ConsulUtil(object):
    def __init__(self):
        self.cns = c.Consul()

    def get_hax_fid(self):
        serv = self.get_local_service_by_name('hax')
        return Fid.parse(serv.get('ID'))

    def get_ha_fid(self):
        serv = self.get_local_service_by_name('ha')
        return Fid.parse(serv.get('ID'))

    def get_rm_fid(self):
        serv = self.get_local_service_by_name('rm')
        return Fid.parse(serv.get('ID'))

    def get_local_service_by_name(self, name):
        services = self.cns.agent.services()
        for k, v in services.items():
            if v.get('Service') == name:
                return v
        raise RuntimeError('No {} service found in Consul'.format(name))

    def get_hax_endpoint(self):
        my_fid = self.get_hax_fid()
        _, services = self.cns.catalog.service(service='hax')
        data = list(
            map(
                self._to_canonical_service_data,
                filter(lambda x: Fid.parse(x.get('ServiceID')) == my_fid,
                       services)))
        return data[0].get('address')

    def get_leader_session(self):
        _, leader = self.cns.kv.get('leader')
        return leader.get('Session')

    def get_session_node(self, session_id):
        _, sess_details = self.cns.session.info(session_id)
        principal_rm = sess_details.get('Node')
        return principal_rm

    def _to_canonical_service_data(self, service):
        node = service.get('Node')
        fid = service.get('ServiceID')
        address = service.get('Address')
        srv_address = service.get('ServiceAddress')
        srv_port = service.get('ServicePort')
        return {
            'node': node,
            'fid': Fid.parse(fid),
            'address': '{}{}:{}'.format(address, srv_address, srv_port)
        }

    def get_confd_list(self):
        _, services = self.cns.catalog.service(service='confd')

        confd_list = list(
            map(self._to_canonical_service_data, services))
        return confd_list
