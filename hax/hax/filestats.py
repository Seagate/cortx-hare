import datetime
import logging
import time

from hax.exception import HAConsistencyException
from hax.halink import HaLink, log_exception
from hax.types import FsStatsWithTime, StoppableThread
from typing import List
from hax.util import ConsulUtil


class FsStatsUpdater(StoppableThread):
    def __init__(self, halink: HaLink, interval_sec=5):
        super().__init__(target=self._execute,
                         name='fs-stats-updater',
                         args=(halink, ))
        self.stopped = False
        self.consul = ConsulUtil()
        self.interval_sec = interval_sec

    def stop(self) -> None:
        logging.debug('Stop signal received')
        self.stopped = True

    @log_exception
    def _execute(self, halink: HaLink):
        try:
            ffi = halink._ffi
            logging.info('filesystem stats updater thread has started')
            ffi.adopt_motr_thread()
            self._ensure_motr_all_started()
            halink.start_rconfc()
            logging.info('rconfc is initialized, FS stats can be polled now')
            while not self.stopped:
                started = self._ioservices_running()
                if not all(started):
                    self.stopped = True
                    continue
                stats = halink.get_filesystem_stats()
                logging.debug('FS stats are as follows: %s', stats)
                now_time = datetime.datetime.now()
                data = FsStatsWithTime(stats=stats,
                                       timestamp=now_time.timestamp(),
                                       date=now_time.isoformat())
                try:
                    self.consul.update_fs_stats(data)
                except HAConsistencyException:
                    logging.debug(
                        'Failed to update Consul KV '
                        'due to an intermittent error. The error is '
                        'swallowed since new attempts will be made '
                        'timely')
                time.sleep(self.interval_sec)
        except Exception:
            logging.exception('Aborting due to an error')
        finally:
            logging.debug('Releasing motr-related resources for this thread')
            ffi.shun_motr_thread()
            logging.debug('filesystem stats updater thread exited')

    def _ioservices_running(self) -> List[bool]:
        statuses = self.consul.get_m0d_statuses()
        logging.debug('The following statuses received: %s', statuses)
        started = ['M0_CONF_HA_PROCESS_STARTED' == v[1] for v in statuses]
        return started

    def _ensure_motr_all_started(self):
        while True:
            started = self._ioservices_running()
            if all(started):
                logging.debug(
                    'According to Consul all confds have been started')
                return
            time.sleep(5)
