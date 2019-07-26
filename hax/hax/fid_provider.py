import consul as c
from hax.types import Fid

SERVICE_CONTAINER = 0x7300000000000001


# FIXME [KN] Rename the class to something more meaningful (ConsulUtil?)
class FidProvider(object):
    def __init__(self):
        self.cns = c.Consul()

    def get_hax_fid(self):
        services = self.cns.agent.services()
        for k, v in services.items():
            if v.get('Service') == 'hax':
                return Fid.parse(k)
        raise RuntimeError('No hax service found in Consul')

    def get_leader_session(self):
        _, leader = self.cns.kv.get('leader')
        return leader.get('Session')

    def get_session_node(self, session_id):
        _, sess_details = self.cns.session.info(session_id)
        principal_rm = sess_details.get('Node')
        return principal_rm

    def _service_to_confd(self, service):
        node = service.get('Node')
        fid = service.get('ServiceID')
        address = service.get('Address')
        srv_address = service.get('ServiceAddress')
        srv_port = service.get('ServicePort')
        return {
            'node':
            node,
            'fid':
            Fid.parse(fid),
            'address':
            '{}{}:{}'.format(address, srv_address, srv_port)
        }

    def get_confd_list(self):
        _, services = self.cns.catalog.service(service='confd')

        confd_list = list(
            map(self._service_to_confd,
                filter(lambda x: x.get('ServiceName') == 'confd', services)))
        return confd_list
