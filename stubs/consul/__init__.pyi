from typing import Any, Tuple, Dict, List

# This is a stub file for `python-consul` module so that mypy will be able
# to validate the code leveraging the library.
#
# NOTE: The stub is not complete so whenever hax starts using more functions
# from the library, the developers are encouraged to improve and extend this stub.

class Consul:
    agent: Agent
    catalog: Catalog
    health: Health
    kv: KV
    session: Session
    txn: Txn

class Health:
    def node(
        self,
        node: str,
        index: int = None,
        wait: str = None,
        dc: str = None,
        token: str = None,
    ) -> Tuple[int, List[Dict[str, Any]]]: ...

class Catalog:
    def nodes(
        self,
        index: int = None,
        wait: str = None,
        consistency: str = None,
        dc: str = None,
        near: str = None,
        token: str = None,
        node_meta: Dict[str, str] = None,
    ) -> Tuple[int, List[Dict[str, Any]]]: ...
    def service(
        self,
        service: str,
        index: int = None,
        wait: str = None,
        tag: str = None,
        consistency: str = None,
        dc: str = None,
        near: str = None,
        token: str = None,
    ) -> Tuple[int, List[Dict[str, Any]]]: ...
    def services(
        self,
        index: int = None,
        wait: str = None,
        tag: str = None,
        consistency: str = None,
        dc: str = None,
        near: str = None,
        token: str = None,
    ) -> Tuple[int, Dict[str, List[Any]]]: ...

class Agent:
    def self(self) -> Dict[str, Any]: ...

class KV:
    def get(
        self,
        key: str,
        index: int = None,
        recurse: bool = False,
        wait: str = None,
        token: str = None,
        keys: bool = False,
        separator: str = None,
        dc: str = None,
    ) -> Tuple[int, Any]: ...
    def put(
        self,
        key: str,
        value: str,
        cas: int = None,
        flags: int = None,
        acquire: str = None,
        release: str = None,
        token: str = None,
        dc: str = None,
    ) -> bool: ...

class Session:
    def info(
        self,
        session_id: str,
        index: int = None,
        wait: str = None,
        consistency: str = None,
        dc: str = None,
    ) -> Tuple[int, Any]: ...

class ConsulException(Exception): ...

class Txn:
    def put(self, payload: List[Dict[str, Any]]) -> bool: ...
