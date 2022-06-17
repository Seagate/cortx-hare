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

import json
import logging
from math import ceil
import re
from threading import Event
from typing import Dict, List, Optional, Tuple
from hax.exception import (BytecountException, HAConsistencyException,
                           InterruptedException)
from hax.motr import Motr, log_exception
from hax.types import (ByteCountStats, Fid, ObjHealth, PverInfo,
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
                                       Dict[str, PverInfo]]:
        '''
        Storing a map of pver_fid and its state.

        Ex of pver state:
        PverInfo(fid=0x7600000000000001:0x3e, state=0,
        data_units=1, parity_units=0, pool_width=10, unit_size=0)

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
                if p_ver not in pver_items:
                    pver_info: PverInfo = motr.get_pver_status(
                        Fid.parse(p_ver))
                    pver_items[p_ver] = pver_info
            LOG.debug('Received pool version and status: %s', pver_items)
        return pver_items

    def _calculate_bc_per_pver(
            self,
            pver_state: Dict[str, PverInfo]) -> Dict[str, int]:
        """
        Aggregate all the bytecount based on pver fid.

        Based on bytecount data saved in consul KV, aggregate all the
        bytecount based on pver fid. Discard the parity buffer count based
        on that pver configuration and return the map of pver fid : bytecount.

        Pver data is stored in consul kv in format
        key = ioservices/0x7200000000000001:0x20/pvers/
              0x7600000000000001:0x6/users/1
        value = {"bc": 4096, "object_cnt": 1}
        """
        pver_bc: Dict[str, int] = {}
        pver_items = self.consul.kv.kv_get('ioservices/', recurse=True)
        regex = re.compile(
            '^ioservices\\/.*\\/pvers\\/([^/]+)')
        if pver_items:
            for pver in pver_items:
                match_result = re.match(regex, pver['Key'])
                if not match_result:
                    continue
                byte_count = json.loads(pver['Value'].decode())['bc']
                pver_fid: str = match_result.group(1)
                if pver_fid in pver_bc:
                    pver_bc[pver_fid] += byte_count
                else:
                    pver_bc[pver_fid] = byte_count

        LOG.debug('Bytecount with parity buffer: %s', pver_bc)

        bc_without_parity: Dict[str, int] = {}
        for pver, bc in pver_bc.items():
            bc_without_parity[pver] = \
                bc - self._get_parity_buffers(bc, pver_state[pver])
        LOG.debug('Bytecount without parity buffer: %s', bc_without_parity)
        return bc_without_parity

    def _get_parity_buffers(self, bc: int, state: PverInfo) -> int:
        """
        Calculate the parity buffer count based on pool configuration.
        """
        tot_units = state.data_units + state.parity_units
        bytes_per_unit = ceil(bc / tot_units)
        return bytes_per_unit * state.parity_units

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
                try:
                    for ios, status in processes:
                        if status == ObjHealth.OK:
                            byte_count: ByteCountStats = \
                                motr.get_proc_bytecount(ios)
                            LOG.debug('Received bytecount: %s', byte_count)
                            if not byte_count:
                                continue
                            self.consul.update_pver_bc(byte_count)

                    pver_items = self._get_pver_with_pver_status(motr)
                    if not pver_items:
                        continue
                    pver_bc = self._calculate_bc_per_pver(pver_items)
                    self.consul.update_bc_for_dg_category(pver_bc, pver_items)
                except HAConsistencyException:
                    LOG.exception('Failed to update Consul KV '
                                  'due to an intermittent error. The '
                                  'error is swallowed since new attempts '
                                  'will be made timely')
                except BytecountException as e:
                    LOG.exception('Failed due to %s. Aborting this iteration.'
                                  ' Waiting for next attempt.', e.message)
                wait_for_event(self.event, self.interval_sec)
        except InterruptedException:
            # No op. _sleep() has interrupted before the timeout exceeded:
            # the application is shutting down.
            # There are no resources that we need to dispose specially.
            pass
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.exception('byte-count updater thread exited')
