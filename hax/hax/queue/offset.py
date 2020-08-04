import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from hax.util import ConsulKVBasic, repeat_if_fails


def get_key_by_node(prefix: str, node_name: str):
    return f'{prefix}/{node_name}/last-read-epoch'


class OffsetStorage:
    """
    Manages the storage of last-read message offsets (epochs)
    for the given consumer node.
    """
    def __init__(self,
                 node_name: str,
                 key_prefix: str = '',
                 kv: Optional[ConsulKVBasic] = None):
        self.node_name = node_name
        self.kv = kv or ConsulKVBasic()
        self.key_prefix = key_prefix

    @repeat_if_fails()
    def mark_last_read(self, message_epoch: int) -> None:
        key = get_key_by_node(self.key_prefix, self.node_name)
        logging.debug('Marking epoch %s as read', str(message_epoch))
        result = self.kv.kv_put(key, str(message_epoch))
        logging.debug('Success? %s', result)

    @repeat_if_fails()
    def get_last_read_epoch(self) -> int:
        key = get_key_by_node(self.key_prefix, self.node_name)
        raw = self.kv.kv_get(key)
        if not raw:
            return -1
        value = raw['Value']

        return int(value) if value is not None else -1


class InboxFilter:
    def __init__(self, offset_mgr: OffsetStorage):
        self.offset_mgr = offset_mgr

    def process(
            self,
            raw_input: List[Dict[str,
                                 Optional[str]]]) -> List[Tuple[int, Any]]:
        def to_tuple(value: Dict[str, Any]) -> Tuple[int, Any]:
            key = value['Key']
            match = re.match(r'^.*\/(\d+)$', key)
            assert match
            key = int(match.group(1))
            v = value['Value']
            return (key, v)

        offset = self.offset_mgr.get_last_read_epoch()
        logging.debug('Last read epoch: %s', offset)
        messages = [to_tuple(item) for item in raw_input]
        messages.sort(key=lambda x: x[0])
        return list(filter(lambda x: x[0] > offset, messages))
