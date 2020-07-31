from typing import Optional

from hax.util import ConsulKVBasic, repeat_if_fails


def get_key_by_node(prefix: str, node_name: str):
    return f'{prefix}/{node_name}/last-read-epoch'


class OffsetStorage:
    """
    Manages the storage of last-read message offsets (epochs).
    """
    def __init__(self,
                 node_name: str,
                 key_prefix: str = '',
                 kv: Optional[ConsulKVBasic] = None):
        self.node_name = node_name
        self.kv = kv or ConsulKVBasic()
        self.key_prefix = key_prefix

    @repeat_if_fails
    def mark_last_read(self, message_epoch: int) -> None:
        key = get_key_by_node(self.key_prefix, self.node_name)
        self.kv.kv_put(key, str(message_epoch))
