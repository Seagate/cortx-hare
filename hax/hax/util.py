import consul as c
import psutil
from hax.exception import HAConsistencyException
from hax.types import Fid

SERVICE_CONTAINER = 0x7300000000000001


class ConsulUtil(object):
    def __init__(self):
        self.cns = c.Consul()
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
        hostname = self.cns.agent.self().get('Config').get('NodeName')
        return hostname

    def get_local_service_by_name(self, name):
        hostname = self.get_my_nodename()

        _, service = self.cns.catalog.service(service=name)
        srv = list(filter(lambda x: x.get('Node') == hostname, service))
        if not len(srv):
            raise HAConsistencyException(
                'No {} service found in Consul at Node={}'.format(
                    name, hostname))
        return srv[0]

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
        session = leader.get('Session')
        if not session:
            raise HAConsistencyException(
                'Could not get the leader from Consul')
        return session

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

        confd_list = list(map(self._to_canonical_service_data, services))
        return confd_list

    def update_process_status(self, event):
	# Remove commented code if not required.
        #pid = event.chp_pid
        #process_name = "unknown"
        #if pid != 0:
            #process = psutil.Process(pid)
            #process_name = process.name()
        #node = self.get_my_nodename()

        #key = 'm0d-process/{}/{}_{}'.format(node, event.fid, process_name)
        key = 'service/{}'.format(event.fid)
        status_value = self.get_status_line(event.chp_event)
        self.cns.kv.put(key, status_value)

    def get_status_line(self, event_type):
        return self.event_map[event_type]
