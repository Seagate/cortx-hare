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

from typing import Any, Tuple, Dict, List, Optional

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
        index: Optional[int] = None,
        wait: Optional[str] = None,
        dc: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Tuple[int, List[Dict[str, Any]]]: ...
    def service(
        self,
        service: str,
        index: Optional[int] = None,
        wait: Optional[str] = None,
        dc: Optional[str] = None,
        near: Optional[str] = None,
        token: Optional[str] = None,
        node_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, List[Dict[str, Any]]]: ...

class Catalog:
    def nodes(
        self,
        index: Optional[int] = None,
        wait: Optional[str] = None,
        consistency: Optional[str] = None,
        dc: Optional[str] = None,
        near: Optional[str] = None,
        token: Optional[str] = None,
        node_meta: Dict[str, str] = None,
    ) -> Tuple[int, List[Dict[str, Any]]]: ...
    def service(
        self,
        service: str,
        index: Optional[int] = None,
        wait: Optional[str] = None,
        tag: Optional[str] = None,
        consistency: Optional[str] = None,
        dc: Optional[str] = None,
        near: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Tuple[int, List[Dict[str, Any]]]: ...
    def services(
        self,
        index: Optional[int] = None,
        wait: Optional[str] = None,
        tag: Optional[str] = None,
        consistency: Optional[str] = None,
        dc: Optional[str] = None,
        near: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Tuple[int, Dict[str, List[Any]]]: ...

class Agent:
    def self(self) -> Dict[str, Any]: ...

class KV:
    def get(
        self,
        key: str,
        index: Optional[int] = None,
        recurse: Optional[bool] = False,
        wait: Optional[str] = None,
        token: Optional[str] = None,
        keys: Optional[bool] = False,
        separator: Optional[str] = None,
        dc: Optional[str] = None,
    ) -> Tuple[int, Any]: ...
    def put(
        self,
        key: str,
        value: str,
        cas: Optional[int] = None,
        flags: Optional[int] = None,
        acquire: Optional[str] = None,
        release: Optional[str] = None,
        token: Optional[str] = None,
        dc: Optional[str] = None,
    ) -> bool: ...

class Session:
    def info(
        self,
        session_id: str,
        index: Optional[int] = None,
        wait: Optional[str] = None,
        consistency: Optional[str] = None,
        dc: Optional[str] = None,
    ) -> Tuple[int, Any]: ...

class ConsulException(Exception): ...

class Txn:
    def put(self, payload: List[Dict[str, Any]]) -> bool: ...
