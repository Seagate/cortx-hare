from abc import ABC, abstractmethod
from typing import List, NamedTuple, Optional

Credentials = NamedTuple('Credentials', [('username', str), ('password', str)])

Node = NamedTuple('Node', [('name', str), ('online', bool), ('shutdown', bool),
                           ('standby', bool), ('unclean', bool),
                           ('resources_running', int)])

Resource = NamedTuple('Resource', [('id', str), ('resource_agent', str),
                                   ('role', str), ('target_role', str),
                                   ('active', bool), ('orphaned', bool),
                                   ('blocked', bool), ('managed', bool),
                                   ('failed', bool), ('failure_ignored', bool),
                                   ('nodes_running_on', int)])


class PcsConnector(ABC):
    credentials = None

    @abstractmethod
    def get_nodes(self) -> List[Node]:
        pass

    @abstractmethod
    def standby_node(self, node_name: str) -> None:
        pass

    @abstractmethod
    def unstandby_node(self, node_name: str) -> None:
        pass

    @abstractmethod
    def get_cluster_name(self) -> str:
        pass

    @abstractmethod
    def standby_all(self) -> None:
        pass

    @abstractmethod
    def unstandby_all(self) -> None:
        pass

    @abstractmethod
    def shutdown_node(self, node_name: str) -> None:
        pass

    @abstractmethod
    def get_resources(self) -> List[Resource]:
        pass

    @abstractmethod
    def get_stonith_resources(self) -> List[Resource]:
        pass

    @abstractmethod
    def disable_resource(self, resource: Resource) -> None:
        pass

    @abstractmethod
    def enable_resource(self, resource: Resource) -> None:
        pass

    @abstractmethod
    def ensure_authorized(self) -> None:
        pass

    def set_credentials(self, credentials: Credentials):
        self.credentials = credentials

    def get_credentials(self) -> Optional[Credentials]:
        return self.credentials
