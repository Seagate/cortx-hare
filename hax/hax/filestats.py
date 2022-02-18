# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#

import datetime
import logging
from threading import Event

from hax.exception import HAConsistencyException, InterruptedException
from hax.motr import Motr, log_exception
from hax.types import FsStatsWithTime, StoppableThread
from hax.util import ConsulUtil, wait_for_event

LOG = logging.getLogger('hax')


class FsStatsUpdater(StoppableThread):
    def __init__(self, motr: Motr, consul_util: ConsulUtil, interval_sec=5):
        super().__init__(target=self._execute,
                         name='fs-stats-updater',
                         args=(motr, ))
        self.stopped = False
        self.consul = consul_util
        self.interval_sec = interval_sec
        self.event = Event()

    def stop(self) -> None:
        LOG.debug('Stop signal received')
        self.stopped = True
        self.event.set()

    @log_exception
    def _execute(self, motr: Motr):
        try:
            LOG.info('filesystem stats updater thread has started')
            while not self.stopped:
                if not self.consul.am_i_rc():
                    wait_for_event(self.event, self.interval_sec)
                    continue
                if (not motr.is_spiel_ready() or (
                        not all(self.consul.ensure_ioservices_running()))):
                    wait_for_event(self.event, self.interval_sec)
                    continue
                stats = motr.get_filesystem_stats()
                if not stats:
                    continue
                LOG.debug('FS stats are as follows: %s', stats)
                now_time = datetime.datetime.now()
                data = FsStatsWithTime(stats=stats,
                                       timestamp=now_time.timestamp(),
                                       date=now_time.isoformat())
                try:
                    self.consul.update_fs_stats(data)
                except HAConsistencyException:
                    LOG.debug('Failed to update Consul KV '
                              'due to an intermittent error. The '
                              'error is swallowed since new attempts '
                              'will be made timely')
                wait_for_event(self.event, self.interval_sec)
        except InterruptedException:
            # No op. _sleep() has interrupted before the timeout exceeded:
            # the application is shutting down.
            # There are no resources that we need to dispose specially.
            pass
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.debug('filesystem stats updater thread exited')
