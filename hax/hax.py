from hax.halink import HaLink
from hax.server import run_server, kv_publisher_thread
from hax.types import Fid
from queue import Queue
from threading import Thread
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
    setup_logging()
    q = Queue(maxsize=1000)
    t = run_publisher_thread(q)
    l = HaLink(node_uuid="This is a test", queue=q)
    run_server(q, thread_to_wait=t, halink=l)

    # l.start("endpoint", Fid(3,4), Fid(5,6), Fid(0xDEADBEEF, 7))


if __name__ == "__main__":
    main()
