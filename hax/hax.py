from hax.halink import HaLink
from hax.server import run_server, kv_handler_thread
from queue import Queue
from threading import Thread
from hax.util import ConsulUtil, SERVICE_CONTAINER
import logging

from hax.types import Fid


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] {%(threadName)s} %(message)s')


def run_handler_thread(q: Queue, ha_link: HaLink):
    t = Thread(target=kv_handler_thread, args=(q, ha_link))
    t.start()
    return t


def main():
    # Note: no logging must happen before this call.
    # Otherwise the log configuration will not apply.
    setup_logging()

    # [KN] The elements in the queue will appear if
    # 1. A callback is invoked from ha_link (this will happen in a mero
    #    thread which must be free ASAP)
    # 2. The main thread is being interrupted (e.g. by SIGTERM) and "Die"
    #    must be sent to the processing thread
    # [KN] The messages are consumed by Python thread created by run_handler_thread function.
    #
    # [KN] Note: The server is launched in the main thread.
    q = Queue(maxsize=1000)

    # [KN] The fid of the hax service is taken from Consul
    util = ConsulUtil()
    hax_ep = util.get_hax_endpoint()
    hax_fid = util.get_hax_fid()
    ha_fid = util.get_ha_fid()
    rm_fid = util.get_rm_fid()

    # [KN] ..while two other ones are auto-generated
    #ha_fid = hax_fid.get_copy()
    #ha_fid.container = SERVICE_CONTAINER
    #rm_fid = ha_fid.get_copy()
    #rm_fid.key = rm_fid.key + 1

    # The node UUID is simply random
    l = HaLink(node_uuid="d63141b1-a7f7-4258-b22a-59fda4ad86d1",
               queue=q,
               rm_fid=rm_fid)
    #pfid = Fid.parse("1:0")
    #hafid = Fid.parse("5:0")
    #rmfid = Fid.parse("4:0")
    t = run_handler_thread(q, l)

    try:
        l.start(hax_ep, process=hax_fid, ha_service=ha_fid, rm_service=rm_fid)
        # [KN] This is a blocking call. It will work until the program is
        # terminated by signal
        l.test_broadcast()
        run_server(q, thread_to_wait=t, halink=l)
    finally:
        l.close()


if __name__ == "__main__":
    main()
