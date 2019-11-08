#!/usr/bin/env python3

import logging
from queue import Queue

from hax.ffi import HaxFFI
from hax.halink import HaLink
from hax.handler import ConsumerThread
from hax.server import run_server
from hax.types import Fid
from hax.util import ConsulUtil

__all__ = ['main']


def _setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] {%(threadName)s} %(message)s')


def _run_qconsumer_thread(queue: Queue, ffi: HaxFFI):
    thread = ConsumerThread(queue, ffi)
    thread.start()
    return thread


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
    hax_ep: str = util.get_hax_endpoint()
    hax_fid: Fid = util.get_hax_fid()
    ha_fid: Fid = util.get_ha_fid()
    rm_fid: Fid = util.get_rm_fid()

    logging.info('Welcome to HaX')
    logging.info(f'Setting up ha_link interface with the options as follows: '
                 f'hax fid = {hax_fid}, hax endpoint = {hax_ep}, '
                 f'HA fid = {ha_fid}, RM fid = {rm_fid}')

    ffi = HaxFFI()
    halink = HaLink(queue=q, rm_fid=rm_fid, ffi=ffi)
    thread = _run_qconsumer_thread(q, ffi)

    try:
        halink.start(hax_ep,
                     process=hax_fid,
                     ha_service=ha_fid,
                     rm_service=rm_fid)
        logging.info('ha_link connection has been established')
        # [KN] This is a blocking call. It will work until the program is
        # terminated by signal
        run_server(thread_to_wait=thread, halink=halink)
    finally:
        halink.close()


if __name__ == '__main__':
    main()
