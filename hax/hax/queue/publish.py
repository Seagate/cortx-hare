from typing import Any, Dict, NamedTuple, Optional

import simplejson
from hax.util import ConsulKVBasic, TxPutKV, repeat_if_fails

# XXX do we want to make payload definition more strict?
# E.g. there could be a type hierarchy for payload objects that depends
# on the type name.
Message = NamedTuple('Message', [('message_type', str),
                                 ('payload', Dict[str, Any])])


class Publisher:
    queue_prefix: str = ''

    def __init__(self,
                 queue_prefix: str,
                 kv: Optional[ConsulKVBasic] = None,
                 epoch_key: str = 'epoch'):
        self.queue_prefix = queue_prefix
        self.kv = kv or ConsulKVBasic()
        self.epoch_key = epoch_key

    @repeat_if_fails(wait_seconds=0.1)
    def publish(self, message_type: str, payload: str) -> int:
        """
        Publishes the given message to the queue.
        """
        data = simplejson.loads(payload)
        message = Message(message_type=message_type, payload=data)
        data = simplejson.dumps(message)

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


class BQPublisher(Publisher):
    def __init__(self, kv=None):
        super().__init__('bq', kv=kv)


class EQPublisher(Publisher):
    def __init__(self, kv=None):
        # TODO think of better names for epoch keys in KV
        super().__init__('eq', kv=kv, epoch_key='eq-epoch')
