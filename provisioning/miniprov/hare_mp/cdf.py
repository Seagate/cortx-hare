import os.path as P
import subprocess as S
from dataclasses import dataclass
from string import Template
from typing import Any, Dict, List, Optional, Tuple
from math import floor
import pkg_resources

from hare_mp.store import ValueProvider
from hare_mp.types import (ClusterDesc, DiskRef, DList, Maybe, NodeDesc,
                           PoolDesc, PoolType, ProfileDesc, Protocol, Text,
                           M0ServerDesc, DisksDesc, AllowedFailures)

DHALL_PATH = '/opt/seagate/cortx/hare/share/cfgen/dhall'
DHALL_EXE = '/opt/seagate/cortx/hare/bin/dhall'
DHALL_TO_YAML_EXE = '/opt/seagate/cortx/hare/bin/dhall-to-yaml'


@dataclass
class Layout:
    data: int
    parity: int
    spare: int


@dataclass
class PoolHandle:
    cluster_id: str
    pool_type: str
    storage_ndx: int

    def tuple(self) -> Tuple[str, str, int]:
        # We could have used dataclasses.astuple() instead here but explicit
        # implementation is safer (we can be sure that the method is not
        # broken after somebody has changed the order of fields)
        return (self.cluster_id, self.pool_type, self.storage_ndx)


class CdfGenerator:
    def __init__(self, provider: ValueProvider):
        super().__init__()
        self.provider = provider

    def _get_dhall_path(self) -> str:
        if P.exists(DHALL_PATH):
            return DHALL_PATH
        raise RuntimeError('CFGEN Dhall types not found')

    def _gencdf(self) -> str:
        resource_path = 'dhall/gencdf.dhall'
        raw_content: bytes = pkg_resources.resource_string(
            'hare_mp', resource_path)
        return raw_content.decode('utf-8')

    def _get_cluster_id(self) -> str:
        conf = self.provider

        # We will read 'cluster_id' of 1st 'machine_id' present in server_node
        server_node = conf.get('server_node')
        machine_id = list(server_node.keys())[0]
        cluster_id = server_node[machine_id]['cluster_id']
        return cluster_id

    def _create_node_descriptions(self) -> List[NodeDesc]:
        nodes: List[NodeDesc] = []
        conf = self.provider
        machines: Dict[str, Any] = conf.get('server_node')
        for machine_id in machines.keys():
            nodes.append(self._create_node(machine_id))
        return nodes

    def _get_pool_property(self, pool: PoolHandle, prop_name: str) -> int:
        conf = self.provider
        (cluster_id, pool_type, storage_ndx) = pool.tuple()

        return int(
            conf.get(f'cluster>{cluster_id}>storage_set[{storage_ndx}]>'
                     f'durability>{pool_type}>{prop_name}'))

    def _get_layout(self, pool: PoolHandle) -> Optional[Layout]:
        conf = self.provider
        (cluster_id, pool_type, storage_ndx) = pool.tuple()
        type_value = conf.get(
            f'cluster>{cluster_id}>storage_set[{storage_ndx}]'
            f'>durability>{pool_type}',
            allow_null=True)
        if not type_value:
            return None

        def prop(name: str) -> int:
            return self._get_pool_property(pool, name)

        return Layout(data=prop('data'),
                      spare=prop('spare'),
                      parity=prop('parity'))

    def _get_devices(self, pool: PoolHandle, node: str) -> List[str]:
        conf = self.provider
        pool_type = pool.pool_type
        prop_name = 'data_devices'
        cvg_num = int(conf.get(f'server_node>{node}>storage>cvg_count'))
        all_cvg_devices = []
        if pool_type == 'dix':
            prop_name = 'metadata_devices'
        for i in range(cvg_num):
            all_cvg_devices += conf.get(
                f'server_node>{node}>storage>cvg[{i}]>{prop_name}')
        return all_cvg_devices

    def _get_server_nodes(self, pool: PoolHandle) -> List[str]:
        cid = pool.cluster_id
        i = pool.storage_ndx
        return self.provider.get(
            f'cluster>{cid}>storage_set[{i}]>server_nodes')

    def _validate_pool(self, pool: PoolHandle) -> None:
        layout = self._get_layout(pool)
        if not layout:
            return

        conf = self.provider
        (cluster_id, pool_type, i) = pool.tuple()

        storage_set_name = conf.get(
            f'cluster>{cluster_id}>storage_set[{i}]>name')

        data_devices_count: int = 0
        for node in self._get_server_nodes(pool):
            data_devices_count += len(self._get_devices(pool, node))

        (data, parity, spare) = (layout.data, layout.parity, layout.spare)
        min_width = data + parity + spare
        if data_devices_count and (data_devices_count < min_width):
            raise RuntimeError(
                'Invalid storage set configuration '
                f'(name={storage_set_name}):'
                f'device count ({data_devices_count}) must be not '
                f'less than N+K+S ({min_width})')

    def _add_pool(self, pool: PoolHandle, out_list: List[PoolDesc]) -> None:
        conf = self.provider
        layout = self._get_layout(pool)
        if not layout:
            return
        (cid, pool_type, i) = pool.tuple()
        storage_set_name = conf.get(f'cluster>{cid}>storage_set[{i}]>name')
        pool_name = f'{storage_set_name}__{pool_type}'

        ctrl_failure_allowed = layout.parity

        machine_id = conf.get_machine_id()
        node_count = len(conf.get_storage_set_nodes())
        cvg_per_node = int(conf.get(
            f'server_node>{machine_id}>storage>cvg_count'))

        cvg_per_storage_set = cvg_per_node * node_count

        if layout.data + layout.parity + layout.spare == 0:
            raise RuntimeError('All layout parameters are 0')

        ratio = floor(cvg_per_storage_set / (
                      layout.data + layout.parity + layout.spare))

        if ratio == 0:
            ctrl_failure_allowed = 0
        else:
            ctrl_failure_allowed = layout.parity

        enc_failure_allowed = floor((layout.parity * ratio) / (
                                    cvg_per_node))

        out_list.append(
            PoolDesc(
                name=Text(pool_name),
                disk_refs=Maybe(
                    DList([
                        DiskRef(
                            path=Text(device),
                            node=Maybe(
                                Text(conf.get(f'server_node>{node}>hostname')),
                                'Text'))
                        for node in self._get_server_nodes(pool)
                        for device in self._get_devices(pool, node)
                    ], 'List DiskRef'), 'List DiskRef'),
                data_units=layout.data,
                parity_units=layout.parity,
                spare_units=Maybe(layout.spare, 'Natural'),
                type=PoolType[pool_type],
                allowed_failures=Maybe(AllowedFailures(
                                       site=0,
                                       rack=0,
                                       encl=enc_failure_allowed,
                                       ctrl=ctrl_failure_allowed,
                                       disk=layout.parity),
                                       'AllowedFailures')))

    def _create_pool_descriptions(self) -> List[PoolDesc]:
        pools: List[PoolDesc] = []
        conf = self.provider
        cluster_id = self._get_cluster_id()
        storage_set_count = int(
            conf.get(f'cluster>{cluster_id}>site>storage_set_count'))

        for i in range(storage_set_count):
            for pool_type in ('sns', 'dix'):
                handle = PoolHandle(cluster_id=cluster_id,
                                    pool_type=pool_type,
                                    storage_ndx=i)
                self._validate_pool(handle)
                self._add_pool(handle, pools)

        return pools

    def _create_profile_descriptions(
            self, pool_desc: List[PoolDesc]) -> List[ProfileDesc]:
        profiles: List[ProfileDesc] = []

        profiles.append(
            ProfileDesc(name=Text('Profile_the_pool'),
                        pools=DList([pool.name for pool in pool_desc],
                                    'List Text')))

        return profiles

    def _get_cdf_dhall(self) -> str:
        dhall_path = self._get_dhall_path()
        nodes = self._create_node_descriptions()
        pools = self._create_pool_descriptions()
        profiles = self._create_profile_descriptions(pools)

        params_text = str(
            ClusterDesc(node_info=nodes,
                        pool_info=pools,
                        profile_info=profiles))
        gencdf = Template(self._gencdf()).substitute(path=dhall_path,
                                                     params=params_text)
        return gencdf

    def generate(self) -> str:
        gencdf = self._get_cdf_dhall()

        dhall = S.Popen([DHALL_EXE],
                        stdin=S.PIPE,
                        stdout=S.PIPE,
                        stderr=S.PIPE,
                        encoding='utf8')

        dhall_out, err_d = dhall.communicate(input=gencdf)
        if dhall.returncode:
            raise RuntimeError(f'dhall binary failed: {err_d}')

        to_yaml = S.Popen([DHALL_TO_YAML_EXE],
                          stdin=S.PIPE,
                          stdout=S.PIPE,
                          stderr=S.PIPE,
                          encoding='utf8')

        yaml_out, err = to_yaml.communicate(input=dhall_out)
        if to_yaml.returncode:
            raise RuntimeError(f'dhall-to-yaml binary failed: {err}')
        return yaml_out

    def _get_iface(self, machine_id: str) -> str:
        ifaces = self.provider.get(
            f'server_node>{machine_id}>network>data>private_interfaces')
        if not ifaces:
            raise RuntimeError('No data network interfaces found')
        return ifaces[0]

    def _get_iface_type(self, machine_id: str) -> Optional[Protocol]:
        iface = self.provider.get(
            f'server_node>{machine_id}>network>data>interface_type',
            allow_null=True)
        if iface is None:
            return None
        return Protocol[iface]

    def _get_data_devices(self, machine_id: str, cvg: int) -> DList[Text]:
        store = self.provider
        data_devices = DList(
            [Text(device) for device in store.get(
                f'server_node>{machine_id}>'
                f'storage>cvg[{cvg}]>data_devices')], 'List Text')
        return data_devices

    def _get_metadata_device(self, name: str, cvg: int) -> Text:
        metadata_device = Text(f'/dev/vg_{name}_md{cvg+1}'
                               f'/lv_raw_md{cvg+1}')
        return metadata_device

    def _create_node(self, machine_id: str) -> NodeDesc:
        store = self.provider
        hostname = store.get(f'server_node>{machine_id}>hostname')
        name = store.get(f'server_node>{machine_id}>name')
        iface = self._get_iface(machine_id)
        try:
            no_m0clients = int(store.get(
                'cortx>software>motr>service>client_instances',
                allow_null=True))
        except TypeError:
            no_m0clients = 2
        # We will create 1 IO service entry in CDF per cvg.
        # An IO service entry will use data devices from corresponding cvg.
        # meta data device is currently hardcoded.
        servers = DList([
            M0ServerDesc(
                io_disks=DisksDesc(
                    data=self._get_data_devices(machine_id, i),
                    meta_data=Maybe(
                        self._get_metadata_device(name, i), 'Text')),
                runs_confd=Maybe(False, 'Bool'))
            for i in range(len(store.get(
                f'server_node>{machine_id}>storage>cvg')))
        ], 'List M0ServerDesc')

        # Adding a Motr confd entry per server node in CDF.
        # The `runs_confd` value (true/false) determines if Motr confd process
        # will be started on the node or not.
        servers.value.append(M0ServerDesc(
            io_disks=DisksDesc(
                data=DList([], 'List Text'),
                meta_data=Maybe(None, 'Text')),
            runs_confd=Maybe(True, 'Bool')))

        return NodeDesc(
            hostname=Text(hostname),
            data_iface=Text(iface),
            data_iface_type=Maybe(self._get_iface_type(machine_id), 'P'),
            m0_servers=Maybe(servers, 'List M0ServerDesc'),
            #
            # [KN] This is a hotfix for singlenode deployment
            # TODO in the future the value must be taken from a correct
            # ConfStore key (it doesn't exist now).
            s3_instances=int(
                store.get(f'server_node>{machine_id}>s3_instances')),
            client_instances=no_m0clients)
