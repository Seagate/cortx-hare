import consul
import base64


# FIXME not finished
class Queue:
    def __init__(self):
        self.client = consul.Consul()

    def _get_queue_key(self):
        return 'BQ'

    def _get_epoch_key(self):
        return 'BQ_epoch'

    def _get_committed_epoch(self):
        k = self._get_epoch_key()
        kv = self.client.kv
        done = False
        prev_value = 0
        while not done:
            index, data = kv.get(k)

            prev_value = 0
            if (data is not None):
                prev_value = int(data['Value'])
            # XXX research whether index is the same to data['ModifyIndex']
            done = kv.put(k, str(prev_value + 1), cas=str(index + 1))
        return prev_value

    def send(self, str_value):
        epoch = self._get_committed_epoch()
        k = self._get_queue_key()
        k = '{}/{}'.format(k, epoch)
        msg = self._format(str_value)
        self.client.kv.put(k, msg)

    def _format(self, str_value):
        b = bytes(str_value, 'utf-8')
        return base64.b64encode(b)

