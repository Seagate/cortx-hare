from typing import Optional

from hax.util import ConsulKVBasic, repeat_if_fails


class EpochProvider:
    def __init__(self,
                 key: str = 'epoch',
                 consul: Optional[ConsulKVBasic] = None):
        self.key = key
        self.kv = consul or ConsulKVBasic()

    @repeat_if_fails(wait_seconds=0.1)
    def get_next(self) -> int:
        """
        Evaluates and persists the new epoch value based on Consul KV
        CAS mechanism.
        """
        while True:
            index, value = self.kv.kv_get_raw(self.key)
            value = int(value['Value'])
            next_value: int = value + 1
            ok = self.kv.kv_put(self.key, str(next_value), cas=index)
            if ok:
                return next_value

    @repeat_if_fails(wait_seconds=0.1)
    def get_current(self) -> int:
        """
        Returns the current epoch value without changing it.
        """
        _, value = self.kv.kv_get_raw(self.key)
        return int(value['Value'])


class Publisher:
    queue_prefix: str = ''

    def __init__(self,
                 queue_prefix: str,
                 kv: Optional[ConsulKVBasic] = None,
                 epoch_key: str = 'epoch'):
        self.queue_prefix = queue_prefix
        self.kv = kv or ConsulKVBasic()
        self.provider = EpochProvider(consul=self.kv, key=epoch_key)

    @repeat_if_fails(wait_seconds=0.1)
    def publish(self, data: str) -> None:
        epoch = self.provider.get_next()
        new_key = f'{self.queue_prefix}/{epoch}'
        self.kv.kv_put(new_key, data)


class BQPublisher(Publisher):
    def __init__(self, kv=None):
        super().__init__('bq', kv=kv)
