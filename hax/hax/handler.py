import logging
import time
from queue import Empty, Queue

from hax.ffi import HaxFFI
from hax.message import EntrypointRequest, HaNvecGetEvent, ProcessEvent
from hax.util import ConsulUtil, repeat_if_fails
from hax.types import StoppableThread


class ConsumerThread(StoppableThread):
    def __init__(self, q: Queue, hax_ffi: HaxFFI):
        super().__init__(target=self._do_work,
                         name='qconsumer',
                         args=(q, hax_ffi))
        self.is_stopped = False
        self.consul = ConsulUtil()

    def stop(self) -> None:
        self.is_stopped = True

    def _do_work(self, q: Queue, ffi: HaxFFI):
        logging.info('Handler thread has started')
        ffi.adopt_motr_thread()

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

                    logging.debug('Got %s message from queue', item)
                    if isinstance(item, EntrypointRequest):
                        ha_link = item.ha_link_instance
                        # While replying any Exception is catched. In such a
                        # case, the motr process will receive EAGAIN and
                        # hence will need to make new attempt by itself
                        ha_link.send_entrypoint_request_reply(item)
                    elif isinstance(item, ProcessEvent):
                        fn = self.consul.update_process_status
                        # If a consul-related exception appears, it will
                        # be processed by repeat_if_fails.
                        #
                        # This thread will become blocked until that
                        # intermittent error gets resolved.
                        decorated = (repeat_if_fails(wait_seconds=5))(fn)
                        decorated(item.evt)
                    elif isinstance(item, HaNvecGetEvent):
                        fn = item.ha_link_instance.ha_nvec_get_reply
                        # If a consul-related exception appears, it will
                        # be processed by repeat_if_fails.
                        #
                        # This thread will become blocked until that
                        # intermittent error gets resolved.
                        decorated = (repeat_if_fails(wait_seconds=5))(fn)
                        decorated(item)
                    else:
                        logging.warning('Unsupported event type received: %s',
                                        item)
                except StopIteration:
                    raise
                except Exception:
                    # no op, swallow the exception
                    logging.exception('**ERROR**')
        except StopIteration:
            ffi.shun_motr_thread()
        finally:
            logging.info('Handler thread has exited')
