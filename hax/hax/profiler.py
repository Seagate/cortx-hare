import logging
import psutil
import os

from threading import Event

from hax.exception import InterruptedException
from hax.motr import log_exception
from hax.types import StoppableThread

LOG = logging.getLogger('hax')


class Profiler(StoppableThread):

    """
    Hax Profiler thread that periodically logs hax's cpu and
    memory usage.
    """
    def __init__(self):
        super().__init__(target=self._execute,
                         name='hax profiler',
                         args=())
        self.stopped = False
        self.event = Event()

    def stop(self) -> None:
        LOG.debug('Stop signal received')
        self.stopped = True
        self.event.set()

    @log_exception
    def _execute(self):
        try:
            LOG.debug('Hax profiler has started')
            while not self.stopped:
                memory_actual = psutil.Process(
                    os.getpid()).memory_full_info()
                # cpu_usage = psutil.Process(
                #      os.getpid()).cpu_percent(interval=2)
                memory_virutal = psutil.virtual_memory()
                # wait_for_event(self.event, 2)
                LOG.info("Actual memory in bytes = {0!r}".format(
                             memory_actual))
                LOG.info("Virtual memory in bytes = {0!r}".format(
                             memory_virutal))
        except InterruptedException:
            # No op. sleep() has interrupted before the timeout exceeded:
            # the application is shutting down.
            # There are no resources that we need to dispose specially.
            pass
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.debug('profiler exited')
