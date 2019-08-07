from hax.halink import HaLink
from hax.ffi import HaxFFI
from hax.server import run_server
from hax.handler import ConsumerThread
from queue import Queue
from hax.util import ConsulUtil
import logging


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] {%(threadName)s} %(message)s')


def run_qconsumer_thread(q: Queue, ffi: HaxFFI):
    t = ConsumerThread(q, ffi)
    t.start()
    return t


def main():
    # Note: no logging must happen before this call.
    # Otherwise the log configuration will not apply.
    setup_logging()

    # [KN] The elements in the queue will appear if
    # 1. A callback is invoked from ha_link (this will happen in a mero
    #    thread which must be free ASAP)
    # 2. TBD: a new HA notification has come form Consul via HTTP
    # [KN] The messages are consumed by Python thread created by run_qconsumer_thread function.
    #
    # [KN] Note: The server is launched in the main thread.
    q = Queue(maxsize=8)

    # [KN] The fid of the hax service is taken from Consul
    util = ConsulUtil()
    hax_ep = util.get_hax_endpoint()
    hax_fid = util.get_hax_fid()
    ha_fid = util.get_ha_fid()
    rm_fid = util.get_rm_fid()

    # The node UUID is simply random
    ffi = HaxFFI()
    l = HaLink(node_uuid="d63141b1-a7f7-4258-b22a-59fda4ad86d1",
               queue=q,
               rm_fid=rm_fid,
               ffi=ffi)
    t = run_qconsumer_thread(q, ffi)

    try:
        l.start(hax_ep, process=hax_fid, ha_service=ha_fid, rm_service=rm_fid)
        # [KN] This is a blocking call. It will work until the program is
        # terminated by signal
        # l.test_broadcast()
        run_server(thread_to_wait=t, halink=l)
    finally:
        l.close()


if __name__ == "__main__":
    main()
