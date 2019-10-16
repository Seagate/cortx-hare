from typing import Any, Tuple, Dict, List

class Consul:
  kv: KV
  catalog: Catalog
  health: Health


class Health:
  def node(self, node: str, index: int = None, wait :str = None, dc: str = None, token: str = None) -> Tuple[int, List[Dict[str, Any]]]: ...

  
class Catalog:
  def nodes(
            self,
            index: int = None,
            wait: str = None,
            consistency: str = None,
            dc: str = None,
            near: str = None,
            token: str = None,
            node_meta: Dict[str, str] = None) -> Tuple[int, List[Dict[str, Any]]]: ...


class KV:
  def get(
          self,
          key: str,
          index: int = None,
          recurse: bool = False,
          wait: str = None,
          token: str = None,
          keys:bool = False,
          separator:str = None,
          dc:str = None) -> Tuple[int, Any]: ...
