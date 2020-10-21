#!/usr/bin/env python3

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

import logging
import sys
from queue import Queue
from typing import NamedTuple

from hax.filestats import FsStatsUpdater
from hax.handler import ConsumerThread
from hax.motr import Motr
from hax.motr.delivery import DeliveryHerald
from hax.motr.ffi import HaxFFI
from hax.server import run_server
from hax.types import Fid
from hax.util import ConsulUtil, repeat_if_fails

__all__ = ['main']

HL_Fids = NamedTuple('HL_Fids', [('hax_ep', str), ('hax_fid', Fid),
                                 ('ha_fid', Fid), ('rm_fid', Fid)])

LOG = logging.getLogger('hax')


def _setup_logging():
    hax_logger = LOG
    hax_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] {%(threadName)s} %(message)s')
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    logging.getLogger('').addHandler(console)
    logging.getLogger('consul').setLevel(logging.WARN)


def _run_qconsumer_thread(queue: Queue, motr: Motr) -> ConsumerThread:
    thread = ConsumerThread(queue, motr)
    thread.start()
    return thread


def _run_stats_updater_thread(motr: Motr) -> FsStatsUpdater:
    thread = FsStatsUpdater(motr, interval_sec=30)
    thread.start()
    return thread


@repeat_if_fails()
def _get_motr_fids(util: ConsulUtil) -> HL_Fids:
    hax_ep: str = util.get_hax_endpoint()
    hax_fid: Fid = util.get_hax_fid()
    ha_fid: Fid = util.get_ha_fid()
    rm_fid: Fid = util.get_rm_fid()
    return HL_Fids(hax_ep, hax_fid, ha_fid, rm_fid)


def main():
    # Note: no logging must happen before this call.
    # Otherwise the log configuration will not apply.
    _setup_logging()

    # [KN] The elements in the queue will appear if
    # 1. A callback is invoked from ha_link (this will happen in a motr
    #    thread which must be free ASAP)
    # 2. A new HA notification has come form Consul via HTTP
    # [KN] The messages are consumed by Python thread created by
    # _run_qconsumer_thread function.
    #
    # [KN] Note: The server is launched in the main thread.
    q = Queue(maxsize=8)

    util: ConsulUtil = ConsulUtil()
    cfg = _get_motr_fids(util)

    LOG.info('Welcome to HaX')
    LOG.info(f'Setting up ha_link interface with the options as follows: '
             f'hax fid = {cfg.hax_fid}, hax endpoint = {cfg.hax_ep}, '
             f'HA fid = {cfg.ha_fid}, RM fid = {cfg.rm_fid}')

    ffi = HaxFFI()
    herald = DeliveryHerald()
    motr = Motr(queue=q, rm_fid=cfg.rm_fid, ffi=ffi, herald=herald)

    # Note that consumer thread must be started before we invoke motr.start(..)
    # Reason: hax process will send entrypoint request and somebody needs
    # to reply it.
    consumer = _run_qconsumer_thread(q, motr)

    try:
        motr.start(cfg.hax_ep,
                   process=cfg.hax_fid,
                   ha_service=cfg.ha_fid,
                   rm_service=cfg.rm_fid)
        LOG.info('Motr API has been started')
        stats_updater = _run_stats_updater_thread(motr)
        # [KN] This is a blocking call. It will work until the program is
        # terminated by signal
        run_server(q, herald, threads_to_wait=[consumer, stats_updater])
    except Exception:
        LOG.exception('Exiting due to an exception')
    finally:
        motr.close()


if __name__ == '__main__':
    main()
