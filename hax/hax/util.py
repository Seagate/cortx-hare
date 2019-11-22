from functools import wraps
import json
import logging
import os
from time import sleep
from typing import Any, Dict, NamedTuple, List

from consul import Consul, ConsulException

from hax.exception import HAConsistencyException
from hax.types import ConfHaProcess, Fid, ObjT

__all__ = ['ConsulUtil', 'create_process_fid']

# XXX What is the difference between `ip_addr` and `address`?
# The names are hard to discern.
ServiceData = NamedTuple('ServiceData', [('node', str), ('fid', Fid),
                                         ('ip_addr', str), ('address', str)])


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


# See enum m0_conf_ha_process_event in Mero source code.
ha_process_events = ('M0_CONF_HA_PROCESS_STARTING',
                     'M0_CONF_HA_PROCESS_STARTED',
                     'M0_CONF_HA_PROCESS_STOPPING',
                     'M0_CONF_HA_PROCESS_STOPPED')


def repeat_if_fails(wait_seconds=5):
    def callable(f):
        @wraps(f)
        def wrapper(*args, **kwds):
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
                    logging.warn(
                        f'Got HAConsistencyException: {e.message}. The'
                        f' attempt will be repeated in {wait_seconds} seconds')
                    sleep(wait_seconds)

        return wrapper

    return callable


class ConsulUtil:
    def __init__(self):
        self.cns: Consul = Consul()

    def _kv_get(self, key: str, **kwargs) -> Any:
        """
        Helper method that should be used by default in this class whenver
        we want to invoke Consul.kv.get()
        """
        assert key
        return self.cns.kv.get(key, **kwargs)[1]

    def _catalog_service_get(self, svc_name: str) -> List[Dict[str, Any]]:
        try:
            return self.cns.catalog.service(service=svc_name)[1]
        except ConsulException as e:
            raise HAConsistencyException('Could not access Consul Catalog')\
                from e

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
        except ConsulException as e:
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
        fidk = self._kv_get(f'm0conf/nodes/{rm_node}/processes/{pfidk}/'
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
        leader = self._kv_get('leader')
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

    def get_confd_list(self) -> List[ServiceData]:
        services = self._catalog_service_get('confd')
        return list(map(mkServiceData, services))

    def get_services_by_parent_process(self, process_fid: Fid) -> List[Fid]:
        pass

    def get_conf_obj_status(self, obj_t: ObjT, fidk: int) -> str:
        # 'node/<node_name>/process/<process_fidk>/service/type'
        node_items = self.cns.kv.get('m0conf/nodes', recurse=True)[1]
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
        except ConsulException as e:
            raise HAConsistencyException(f'Failed to get {node} node health')\
                    from e

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

    def update_process_status(self, event: ConfHaProcess) -> None:
        assert 0 <= event.chp_event < len(ha_process_events), \
            f'Invalid event type: {event.chp_event}'

        try:
            # TODO [KN] improve type stubs!
            data = json.dumps({'state': ha_process_events[event.chp_event]})
            key = f'processes/{event.fid}'
            logging.debug('Setting process status in KV: %s:%s', key, data)
            self.cns.kv.put(  # type: ignore
                # This `type:` directive prevents mypy error:
                #     "KV" has no attribute "put"
                key, data)
        except ConsulException as e:
            raise HAConsistencyException('Failed to put value to KV') from e
