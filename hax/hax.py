from hax.halink import HaLink
from hax.types import Fid
import logging


def setup_logging():
    logging.basicConfig(level=logging.DEBUG)


def main():
    setup_logging()
    l = HaLink(node_uuid="This is a test")
    l.start("endpoint", Fid(3,4), Fid(5,6), Fid(0xDEADBEEF, 7))
    l.test()


if __name__ == "__main__":
    main()
