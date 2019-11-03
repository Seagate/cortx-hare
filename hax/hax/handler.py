import logging
import time
from queue import Empty, Queue
from threading import Thread

from hax.ffi import HaxFFI
from hax.message import EntrypointRequest, HaNvecGetEvent, ProcessEvent
from hax.util import ConsulUtil


class ConsumerThread(Thread):
    def __init__(self, q: Queue, hax_ffi: HaxFFI):
        super().__init__(target=self._do_work,
                         name='qconsumer',
                         args=(q, hax_ffi))
        self.is_stopped = False
        self.consul = ConsulUtil()

    def _do_work(self, q: Queue, ffi: HaxFFI):
        logging.info('Handler thread has started')
        ffi.adopt_mero_thread()

        def pull_msg():
            try:
                return q.get(block=False)
            except Empty:
                return None

        try:
            while True:
                try:
                    logging.debug('Waiting for the next message')

                    item = pull_msg()
                    while item is None:
                        time.sleep(0.2)
                        if self.is_stopped:
                            raise StopIteration()
                        item = pull_msg()

                    logging.debug('Got something from the queue')
                    if isinstance(item, EntrypointRequest):
                        ha_link = item.ha_link_instance
                        ha_link.send_entrypoint_request_reply(item)
                    elif isinstance(item, ProcessEvent):
                        self.consul.update_process_status(item.evt)
                    elif isinstance(item, HaNvecGetEvent):
                        item.ha_link_instance.ha_nvec_get_reply(item)
                    else:
                        logging.warning('Unsupported event type received: %s',
                                        item)
                except StopIteration:
                    raise
                except Exception:
                    # no op, swallow the exception
                    logging.exception('**ERROR**')
        except StopIteration:
            ffi.shun_mero_thread()
        finally:
            logging.info('Handler thread has exited')
