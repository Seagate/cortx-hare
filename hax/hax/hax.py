#!/usr/bin/env python3

import logging
from queue import Queue
from typing import NamedTuple

from hax.ffi import HaxFFI
from hax.filestats import FsStatsUpdater
from hax.halink import HaLink
from hax.handler import ConsumerThread
from hax.server import run_server
from hax.types import Fid
from hax.util import ConsulUtil, repeat_if_fails

__all__ = ['main']

HL_Fids = NamedTuple('HL_Fids', [('hax_ep', str), ('hax_fid', Fid),
                                 ('ha_fid', Fid), ('rm_fid', Fid)])


def _setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] {%(threadName)s} %(message)s')


def _run_qconsumer_thread(queue: Queue, ffi: HaxFFI) -> ConsumerThread:
    thread = ConsumerThread(queue, ffi)
    thread.start()
    return thread


def _run_stats_updater_thread(halink: HaLink) -> FsStatsUpdater:
    thread = FsStatsUpdater(halink, interval_sec=30)
    thread.start()
    return thread


@repeat_if_fails()
def _get_halink_fids(util: ConsulUtil) -> HL_Fids:
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
    # 1. A callback is invoked from ha_link (this will happen in a mero
    #    thread which must be free ASAP)
    # 2. A new HA notification has come form Consul via HTTP
    # [KN] The messages are consumed by Python thread created by
    # _run_qconsumer_thread function.
    #
    # [KN] Note: The server is launched in the main thread.
    q = Queue(maxsize=8)

    util: ConsulUtil = ConsulUtil()
    cfg = _get_halink_fids(util)

    logging.info('Welcome to HaX')
    logging.info(f'Setting up ha_link interface with the options as follows: '
                 f'hax fid = {cfg.hax_fid}, hax endpoint = {cfg.hax_ep}, '
                 f'HA fid = {cfg.ha_fid}, RM fid = {cfg.rm_fid}')

    ffi = HaxFFI()
    halink = HaLink(queue=q, rm_fid=cfg.rm_fid, ffi=ffi)
    consumer = _run_qconsumer_thread(q, ffi)

    try:
        halink.start(cfg.hax_ep,
                     process=cfg.hax_fid,
                     ha_service=cfg.ha_fid,
                     rm_service=cfg.rm_fid)
        logging.info('ha_link connection has been established')
        stats_updater = _run_stats_updater_thread(halink)
        # [KN] This is a blocking call. It will work until the program is
        # terminated by signal
        run_server(threads_to_wait=[consumer, stats_updater], halink=halink)
    finally:
        halink.close()


if __name__ == '__main__':
    main()
