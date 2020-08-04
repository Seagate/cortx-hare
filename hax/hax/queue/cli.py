import logging
import sys

from hax.queue.publish import BQPublisher


def _setup_logging():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s [%(levelname)s] %(message)s')


def main():
    _setup_logging()
    try:
        if len(sys.argv) < 2:
            raise RuntimeError('No message given.')
        message = sys.argv[1]
        pub = BQPublisher()
        offset = pub.publish(message)
        logging.info('Written to epoch: %s', offset)

    except Exception:
        logging.exception('Exiting with failure')
