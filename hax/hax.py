from hax.halink import HaLink
from hax.server import run_server
from hax.types import Fid
from queue import Queue
from threading import Thread
import consul
import logging


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] {%(threadName)s} %(message)s')


def thread_fn(ha: HaLink):
    ha.test()


def kv_publisher_thread(q: Queue):
    logging.info('Publisher thread has started')
    try:
        client = consul.Consul()
        while True:
            item = q.get()
            logging.debug('Sending message to Consul: {}'.format(item))
            # TODO what and where do we actually need to persist to KV?
            # client.kv.put('bq', item)
    finally:
        logging.info('Publisher thread has exited')


def run_publisher_thread(q: Queue):
    t = Thread(target=kv_publisher_thread, args=(q, ))
    t.start()

def main():
    setup_logging()
    q = Queue(maxsize=1000)
    run_publisher_thread(q)
    run_server(q)

    l = HaLink(node_uuid="This is a test")
    # l.start("endpoint", Fid(3,4), Fid(5,6), Fid(0xDEADBEEF, 7))


if __name__ == "__main__":
    main()
