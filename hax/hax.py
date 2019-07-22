from hax.halink import HaLink
from hax.types import Fid
import logging
import threading
import signal

def setup_logging():
    logging.basicConfig(level=logging.DEBUG)


def thread_fn(ha: HaLink):
    ha.test()


def main():
    setup_logging()
    l = HaLink(node_uuid="This is a test")
    # l.start("endpoint", Fid(3,4), Fid(5,6), Fid(0xDEADBEEF, 7))
    logging.info("Invoking threads")

    threads = [None] * 20
    threads = list(map(lambda t: threading.Thread(target=thread_fn, args=(l,)), threads))

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    logging.info("Threads finished")

def handleSignal(signalNumber, frame):
    print('Received:', signalNumber)
    raise SystemExit('Exiting')
    return

if __name__ == "__main__":
    main()
    signal.signal(signal.SIGTERM, handleSignal)
    signal.signal(signal.SIGINT, handleSignal)
    signal.signal(signal.SIGQUIT, handleSignal)

    signal.pause()
