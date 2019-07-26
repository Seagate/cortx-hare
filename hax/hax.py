from hax.halink import HaLink
from hax.server import run_server, kv_publisher_thread
from queue import Queue
from threading import Thread
from hax.fid_provider import FidProvider, SERVICE_CONTAINER
import logging


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] {%(threadName)s} %(message)s')


def run_publisher_thread(q: Queue):
    t = Thread(target=kv_publisher_thread, args=(q, ))
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
    # [KN] The messages are consumed by Python thread created by run_publisher_thread function.
    #
    # [KN] Note: The server is launched in the main thread.
    q = Queue(maxsize=1000)
    t = run_publisher_thread(q)

    # The node UUID is simply random
    l = HaLink(node_uuid="d63141b1-a7f7-4258-b22a-59fda4ad86d1", queue=q)
    # [KN] The fid of the hax service is taken from Consul
    hax_ep = FidProvider().get_hax_endpoint()
    hax_fid = FidProvider().get_hax_fid()

    # [KN] ..while two other ones are auto-generated
    ha_fid = hax_fid.get_copy()
    ha_fid.container = SERVICE_CONTAINER
    rm_fid = ha_fid.get_copy()
    rm_fid.key = rm_fid.key + 1

    # [KN] FIXME the endpoint must be constructed dynamically by the data taken
    # from Consul

    l.start(hax_ep,
            process=hax_fid,
            ha_service=ha_fid,
            rm_service=rm_fid)
    # [KN] This is a blocking call. It will work until the program is
    # terminated by signal
    run_server(q, thread_to_wait=t, halink=l)


if __name__ == "__main__":
    main()
