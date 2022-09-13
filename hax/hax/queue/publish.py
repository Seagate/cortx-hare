from typing import Any, Dict, List, NamedTuple, Optional

import simplejson
from hax.util import KVAdapter, TxPutKV, repeat_if_fails

# XXX do we want to make payload definition more strict?
# E.g. there could be a type hierarchy for payload objects that depends
# on the type name.
Message = NamedTuple('Message', [('message_type', str),
                                 ('payload', Dict[str, Any])])


class Publisher:
    queue_prefix: str = ''

    def __init__(self,
                 queue_prefix: str,
                 kv: Optional[KVAdapter] = None,
                 epoch_key: str = 'epoch'):
        self.queue_prefix = queue_prefix
        self.kv = kv or KVAdapter()
        self.epoch_key = epoch_key

    @staticmethod
    def _get_payload_with_type(message_type: str, payload: str) -> str:
        data = simplejson.loads(payload)
        message = Message(message_type=message_type, payload=data)
        data = simplejson.dumps(message)
        return str(data)

    @repeat_if_fails(wait_seconds=0.1)
    def publish(self, message_type: str, payload: str) -> int:
        """Publishes the given message to the queue."""
        data = Publisher._get_payload_with_type(message_type, payload)

        while True:
            index, value = self.kv.kv_get_raw(self.epoch_key)
            value = int(value['Value'])
            next_epoch: int = value + 1

            new_key = f'{self.queue_prefix}/{next_epoch}'
            ok = self.kv.kv_put_in_transaction([
                TxPutKV(key=self.epoch_key,
                        value=str(next_epoch),
                        cas=int(index)),
                TxPutKV(key=new_key, value=data, cas=None)
            ])
            if ok:
                return next_epoch

    def publish_no_duplicate(self,
                             message_type: str,
                             payload: str,
                             key_suffix: str,
                             checks: Optional[List[TxPutKV]] = None) -> bool:
        """Drop the event if the event is already present in the queue."""
        data = Publisher._get_payload_with_type(message_type, payload)
        # import pdb; pdb.set_trace()
        new_key = f'{self.queue_prefix}/{key_suffix}'
        tx_list = []
        if checks:
            tx_list.extend(checks)
        tx_list.append(TxPutKV(key=new_key, value=data, cas=0))
        ok = self.kv.kv_put_in_transaction(tx_list)
        return ok


class BQPublisher(Publisher):
    def __init__(self, kv=None):
        super().__init__('bq', kv=kv)


class EQPublisher(Publisher):
    def __init__(self, kv=None):
        # TODO think of better names for epoch keys in KV
        super().__init__('eq', kv=kv, epoch_key='eq-epoch')
