from enum import Enum
import json
import os
from typing import Any, Dict, NamedTuple, List

from consul import Consul

from hax.exception import HAConsistencyException
from hax.types import ConfHaProcess, Fid


__all__ = ['ConsulUtil', 'create_process_fid']


# XXX What is the difference between `ip_addr` and `address`?
# The names are hard to discern.
ServiceData = NamedTuple('ServiceData', [('node', str),
                                         ('fid', Fid),
                                         ('ip_addr', str),
                                         ('address', str)])


def mkServiceData(service: Dict[str, Any]) -> ServiceData:
    return ServiceData(node=service['Node'],
                       fid=mk_fid(ObjT.PROCESS,  # XXX s/PROCESS/SERVICE/ ?
                                  int(service['ServiceID'])),
                       ip_addr=service['Address'],
                       address='{}:{}'.format(service['ServiceAddress'],
                                              service['ServicePort']))


ObjT = Enum('ObjT', [
    # There are the only conf object types we care about.
    ('PROCESS', 0x7200000000000001),
    ('SERVICE', 0x7300000000000001)
])
ObjT.__doc__ = 'Mero conf object types and their m0_fid.f_container values'


def mk_fid(obj_t: ObjT, key: int) -> Fid:
    return Fid(obj_t.value, key)


def create_process_fid(key: int) -> Fid:
    return mk_fid(ObjT.PROCESS, key)


# See enum m0_conf_ha_process_event in Mero source code.
ha_process_events = (
    'M0_CONF_HA_PROCESS_STARTING',
    'M0_CONF_HA_PROCESS_STARTED',
    'M0_CONF_HA_PROCESS_STOPPING',
    'M0_CONF_HA_PROCESS_STOPPED'
)


class ConsulUtil:
    def __init__(self):
        self.cns: Consul = Consul()

    def _kv_get(self, key: str) -> Any:
        assert key
        return self.cns.kv.get(key)[1]

    def _service_by_name(self, hostname: str, svc_name: str) -> Dict[str, Any]:
        for svc in self.cns.catalog.service(service=svc_name)[1]:
            if svc['Node'] == hostname:
                return svc
        raise HAConsistencyException(
            f'No {svc_name!r} Consul service found at node {hostname!r}')

    def _local_service_by_name(self, name: str) -> Dict[str, Any]:
        """
        Returns the service data by its name assuming that it runs at the same
        node to the current hax process.
        """
        local_nodename = os.environ.get('HARE_HAX_NODE_NAME') or \
            self.cns.agent.self()['Config']['NodeName']
        return self._service_by_name(local_nodename, name)

    def _service_data(self) -> ServiceData:
        my_fidk = self.get_hax_fid().key
        services = self.cns.catalog.service(service='hax')[1]
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
        fidk = self._kv_get(f'm0conf/nodes/{rm_node}/processes/{pfidk}/'
                            'services/rms')
        return mk_fid(ObjT.SERVICE, int(fidk['Value']))

    def get_hax_endpoint(self) -> str:
        return self._service_data().address

    def get_hax_ip_address(self) -> str:
        return self._service_data().ip_addr

    def get_leader_session(self) -> str:
        leader = self._kv_get('leader')
        try:
            return str(leader['Session'])
        except KeyError:
            raise HAConsistencyException(
                'Could not get the leader from Consul')

    def get_session_node(self, session_id: str) -> str:
        session = self.cns.session.info(session_id)[1]
        return str(session['Node'])  # principal RM

    def get_confd_list(self) -> List[ServiceData]:
        services = self.cns.catalog.service(service='confd')[1]
        return list(map(mkServiceData, services))

    def update_process_status(self, event: ConfHaProcess) -> None:
        assert 0 <= event.chp_event < len(ha_process_events), \
            f'Invalid event type: {event.chp_event}'

        self.cns.kv.put(  # type: ignore
            # This `type:` directive prevents mypy error:
            #     "KV" has no attribute "put"
            f'processes/{event.fid}',
            json.dumps({'state': ha_process_events[event.chp_event]}))
