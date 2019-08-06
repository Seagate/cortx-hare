from threading import Thread
from queue import Queue, Empty
from hax.message import EntrypointRequest
from hax.halink import HaLink
import time
import logging


class ConsumerThread(Thread):
    def __init__(self, q: Queue, ha_link: HaLink):
        super().__init__(target=self._do_work,
                         name='qconsumer',
                         args=(q, ha_link))
        self.is_stopped = False

    def _do_work(self, q: Queue, ha_link: HaLink):
        logging.info('Handler thread has started')
        ha_link.adopt_mero_thread()

        def pull_msg():
            try:
                return q.get(block=False)
            except Empty:
                return None

        try:
            while True:
                logging.debug('Waiting for the next message')

                item = pull_msg()
                while item is None:
                    time.sleep(0.2)
                    if self.is_stopped:
                        raise StopIteration()
                    item = pull_msg()

                logging.debug('Got something from the queue')
                if isinstance(item, EntrypointRequest):
                    ha_link.send_entrypoint_request_reply(item)
                else:
                    logging.debug('Sending message to Consul: {}'.format(
                        item.s))
        except StopIteration:
            ha_link.shun_mero_thread()
            logging.info('Handler thread has exited')
