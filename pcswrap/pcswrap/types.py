from typing import List, NamedTuple
from abc import ABC, abstractmethod

Node = NamedTuple('Node', [('name', str), ('online', bool), ('shutdown', bool),
                           ('standby', bool)])


class PcsConnector(ABC):
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
