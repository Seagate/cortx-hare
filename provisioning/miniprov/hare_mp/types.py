from dataclasses import dataclass, fields
from enum import Enum
from typing import Generic, List, Optional, Sequence, TypeVar

A = TypeVar('A')


@dataclass
class Maybe(Generic[A]):
    value: Optional[A]
    comment: str

    def __str__(self):
        if self.value is None:
            return f'None ({self.comment})'

        return f'Some ({self.value})'

    def get(self):
        return self.value


T = TypeVar('T')


@dataclass
class DList(Sequence[T]):
    value: List[T]
    comment: str

    def __getitem__(self, ndx):
        """Allows using [] operator."""
        return self.value[ndx]

    def __len__(self):
        return len(self.value)

    def __str__(self):
        if not self.value:
            return f'[] : {self.comment}'

        return '[' + ', '.join(str(item) for item in self.value) + ']'


class Protocol(Enum):
    o2ib = 1
    tcp = 2

    def __str__(self):
        return f'P.{self.name}'


class PoolType(Enum):
    sns = 1
    dix = 2
    md = 3

    def __str__(self):
        return f'T.PoolType.{self.name}'


class DhallTuple:
    def __str__(self):
        def v(field):
            return getattr(self, field.name)

        return '{ ' + ', '.join(f'{k.name} = {v(k)}'
                                for k in fields(self)) + ' }'

    def __repr__(self):
        """Machine readable str representation of the DhallTuple object."""
        return self.__str__()


@dataclass
class Text:
    # The only reason why the class is here is that standard Python str type
    # gets stringified with single quotes (while Dhall supports double
    # quotes only).
    s: str

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f'"{self.s}"'


@dataclass(repr=False)
class M0ClientDesc(DhallTuple):
    name: Text
    instances: int


@dataclass(repr=False)
class Disk(DhallTuple):
    path: Maybe[Text]
    size: Maybe[int]
    blksize: Maybe[int]


@dataclass(repr=False)
class DisksDesc(DhallTuple):
    meta_data: Maybe[Text]
    data: DList[Disk]
    log: DList[Disk]


@dataclass(repr=False)
class M0ServerDesc(DhallTuple):
    runs_confd: Maybe[bool]
    io_disks: DisksDesc


@dataclass(repr=False)
class ClientPort(DhallTuple):
    name: Text
    port: int


@dataclass(repr=False)
class ServerPort(DhallTuple):
    name: Text
    port: int


@dataclass(repr=False)
class NetworkPorts(DhallTuple):
    hax: Maybe[int]
    hax_http: Maybe[int]
    m0_server: Maybe[DList[ServerPort]]
    m0_client_s3: Maybe[int]
    m0_client_other: Maybe[DList[ClientPort]]


@dataclass(repr=False)
class NodeDesc(DhallTuple):
    hostname: Text
    node_group: Maybe[Text]
    machine_id: Maybe[Text]
    processorcount: Maybe[int]
    memorysize_mb: Maybe[int]
    data_iface: Text
    data_iface_ip_addr: Maybe[Text]
    data_iface_type: Maybe[Protocol]
    transport_type: Text
    m0_servers: Maybe[DList[M0ServerDesc]]
    m0_clients: Maybe[DList[M0ClientDesc]]
    ports_info: Maybe[NetworkPorts]


@dataclass(repr=False)
class DiskRef(DhallTuple):
    path: Text
    node: Maybe[Text]


@dataclass(repr=False)
class AllowedFailures(DhallTuple):
    site: int
    rack: int
    encl: int
    ctrl: int
    disk: int


@dataclass(repr=False)
class PoolDesc(DhallTuple):
    name: Text
    disk_refs: Maybe[DList[DiskRef]]
    data_units: int
    parity_units: int
    spare_units: Maybe[int]
    type: PoolType
    allowed_failures: Maybe[AllowedFailures]


@dataclass(repr=False)
class ProfileDesc(DhallTuple):
    name: Text
    pools: DList[Text]


@dataclass(repr=False)
class FdmiFilterDesc(DhallTuple):
    client_index: int
    name: Text
    node: Text
    substrings: DList[Text]


@dataclass(repr=False)
class ClusterDesc(DhallTuple):
    create_aux: Maybe[bool]
    node_info: DList[NodeDesc]
    pool_info: DList[PoolDesc]
    profile_info: DList[ProfileDesc]
    fdmi_filter_info: Maybe[List[FdmiFilterDesc]]


@dataclass(repr=False)
class MissingKeyError(Exception):
    key: str
    url: str

    def __str__(self):
        return f"Required key '{self.key}' not found at URL: {self.url}"


@dataclass(repr=False)
class Layout:
    data: int
    parity: int
    spare: int
