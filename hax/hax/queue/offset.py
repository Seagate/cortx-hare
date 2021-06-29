import base64
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from hax.util import KVAdapter, repeat_if_fails

LOG = logging.getLogger('hax')


def get_key_by_node(prefix: str, node_name: str):
    return f'{prefix}/{node_name}'


class OffsetStorage:
    """
    Manages the storage of last-read message offsets (epochs)
    for the given consumer node.
    """
    def __init__(self,
                 node_name: str,
                 key_prefix: str = '',
                 kv: Optional[KVAdapter] = None):
        self.node_name = node_name
        self.kv = kv or KVAdapter()
        self.key_prefix = key_prefix

    @repeat_if_fails()
    def mark_last_read(self, message_epoch: int) -> None:
        key = get_key_by_node(self.key_prefix, self.node_name)
        LOG.debug('Marking epoch %s as read', str(message_epoch))
        self.kv.kv_put(key, str(message_epoch))

    @repeat_if_fails()
    def get_last_read_epoch(self) -> int:
        key = get_key_by_node(self.key_prefix, self.node_name)
        raw = self.kv.kv_get(key)
        if not raw:
            return -1
        value = raw['Value']

        return -1 if value is None else int(value)


class InboxFilter:
    """
    Sorts the received keys in numeric order (instead of alpabetical as
    reported by Consul) and then removes the messages that are already read.
    """
    def __init__(self, offset_mgr: OffsetStorage):
        self.offset_mgr = offset_mgr

    def prepare(
            self,
            raw_input: List[Dict[str,
                                 Optional[str]]]) -> List[Tuple[int, Any]]:
        """
        Guarantees that the returned list contains the messages that were
        not read by the current node so far and that the messages are
        ordered properly.
        """
        def to_tuple(value: Dict[str, Any]) -> Tuple[int, Any]:
            key = value['Key']
            match = re.match(r'^.*\/(\d+)$', key)
            assert match
            key = int(match.group(1))
            # Note: A Consul watch brings JSON with base64-encoded values
            b_value: bytes = base64.b64decode(value['Value'])
            return (key, b_value.decode())

        offset = self.offset_mgr.get_last_read_epoch()
        LOG.debug('Last read epoch: %s', offset)
        messages = [to_tuple(item) for item in raw_input]
        messages.sort(key=lambda x: x[0])
        return [x for x in messages if x[0] > offset]
