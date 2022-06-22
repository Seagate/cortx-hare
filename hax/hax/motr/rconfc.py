import logging
from threading import Event

from hax.exception import InterruptedException
from hax.motr import Motr, log_exception
from hax.types import StoppableThread
from hax.util import wait_for_event
from hax.configmanager import ConfigManager

LOG = logging.getLogger('hax')


class RconfcStarter(StoppableThread):

    """
    A short-lived thread that is intended to start rconfc.

    Effectively, rconfc could have been started in the same thread where Motr
    context is initialized but there is a chance of deadlock (confd quorum
    will not appear until confd's will receive entrypoint reply but that reply
    can happen when Motr is initialized in hax).
    """
    def __init__(self, motr: Motr, consul_util: ConfigManager):
        super().__init__(target=self._execute,
                         name='rconfc-starter',
                         args=(motr, ))
        self.stopped = False
        self.consul = consul_util
        self.event = Event()

    def stop(self) -> None:
        LOG.debug('Stop signal received')
        self.stopped = True
        self.event.set()

    @log_exception
    def _execute(self, motr: Motr):
        try:
            LOG.debug('rconfc starter thread has started')
            self.consul.ensure_motr_all_started(self.event)
            while (not self.stopped) and (not motr.spiel_ready):
                started = self.consul.ensure_ioservices_running()
                if not all(started):
                    wait_for_event(self.event, 5)
                    continue
                result: int = motr.start_rconfc()
                if result == 0:
                    motr.spiel_ready = True
        except InterruptedException:
            # No op. sleep() has interrupted before the timeout exceeded:
            # the application is shutting down.
            # There are no resources that we need to dispose specially.
            pass
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.debug('rconfc starter thread exited')
