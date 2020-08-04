from typing import Optional

from hax.util import ConsulKVBasic, TxPutKV, repeat_if_fails


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
    def publish(self, data: str) -> int:
        """
        Publishes the given message to the queue.
        """
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
