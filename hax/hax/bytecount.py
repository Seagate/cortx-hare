# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
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

import logging
from threading import Event
from typing import Dict, List, Optional, Tuple
from hax.exception import HAConsistencyException, InterruptedException
from hax.motr import Motr, log_exception
from hax.types import (ByteCountStats, Fid, ObjHealth, PverState,
                       StoppableThread)
from hax.util import ConsulUtil, wait_for_event

LOG = logging.getLogger('hax')


class ByteCountUpdater(StoppableThread):
    def __init__(self, motr: Motr, consul_util: ConsulUtil, interval_sec=5):
        super().__init__(target=self._execute,
                         name='byte-count-updater',
                         args=(motr, ))
        self.stopped = False
        self.consul = consul_util
        self.interval_sec = interval_sec
        self.event = Event()

    def stop(self) -> None:
        LOG.debug('Stop signal received')
        self.stopped = True
        self.event.set()

    def _get_pver_with_pver_status(self,
                                   motr: Motr) -> Optional[
                                       Dict[str, PverState]]:
        '''
        Getting a dictionary value of pver and it's state like below example:
        Ex: {'0x7600000000000001:0x8': PverState.M0_CPS_CRITICAL,
             '0x7600000000000001:0x9': PverState.M0_CPS_HEALTHY
            }
        Pver data is stored in consul kv in format
        key = ioservices/0x7200000000000001:0x20/pvers/
              0x7600000000000001:0x6/users/1
        value = {"bc": 4096, "object_cnt": 1}
        '''
        iosservice_items = self.consul.kv.kv_get('ioservices/', recurse=True)
        pver_items = {}
        if iosservice_items:
            for k in iosservice_items:
                p_ver = k['Key'].split('/')[3]
                pver_items[p_ver] = motr.get_pver_status(Fid.parse(p_ver))
            LOG.debug('Received pool version and status: %s', pver_items)
        return pver_items

    @log_exception
    def _execute(self, motr: Motr):
        try:
            LOG.info('byte-count updater thread has started')
            while not self.stopped:
                if not self.consul.am_i_rc():
                    wait_for_event(self.event, self.interval_sec)
                    continue
                if not motr.is_spiel_ready():
                    wait_for_event(self.event, self.interval_sec)
                    continue
                processes: List[Tuple[Fid, ObjHealth]] = \
                    self.consul.get_proc_fids_with_status(['ios'])
                if not processes:
                    continue
                for ios, status in processes:
                    if status == ObjHealth.OK:
                        byte_count: ByteCountStats = motr.get_proc_bytecount(
                            ios)
                        LOG.debug('Received bytecount: %s', byte_count)
                        if not byte_count:
                            continue
                        try:
                            self.consul.update_pver_bc(byte_count)
                        except HAConsistencyException:
                            LOG.debug('Failed to update Consul KV '
                                      'due to an intermittent error. The '
                                      'error is swallowed since new attempts '
                                      'will be made timely')

                wait_for_event(self.event, self.interval_sec)

                pver_items = self._get_pver_with_pver_status(motr)
                if not pver_items:
                    continue
                self.consul.update_bc_for_dg_category(pver_items)
        except InterruptedException:
            # No op. _sleep() has interrupted before the timeout exceeded:
            # the application is shutting down.
            # There are no resources that we need to dispose specially.
            pass
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.debug('byte-count updater thread exited')
