# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

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
    def members(self, wan: bool = False) -> List[Dict[str, Any]]: ...

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
    def destroy(
        self,
        session_id: str
    ) -> bool: ...

class ConsulException(Exception): ...

class Txn:
    def put(self, payload: List[Dict[str, Any]]) -> bool: ...
