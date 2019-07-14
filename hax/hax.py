from hax.halink import HaLink
import logging


def setup_logging():
    logging.basicConfig(level=logging.DEBUG)


def main():
    setup_logging()
    l = HaLink()
    l.start()
    l.test()


if __name__ == "__main__":
    main()
