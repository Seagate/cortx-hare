import logging
import sys
from typing import NamedTuple

import click
from hax.queue.publish import BQPublisher, EQPublisher, Publisher

AppCtx = NamedTuple('AppCtx', [('payload', str), ('type', str),
                               ('publisher', Publisher)])


def _setup_logging():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s [%(levelname)s] %(message)s')


@click.command()
@click.option('-q',
              '--queue',
              default='eq',
              type=click.Choice(['eq', 'bq'], case_sensitive=False))
@click.option('-t', '--message-type', type=str)
@click.argument('payload')
@click.pass_context
def parse_opts(ctx, queue: str, message_type: str, payload: str):
    ctx.ensure_object(dict)
    name = queue.lower()
    types = {'eq': EQPublisher, 'bq': BQPublisher}

    # We're lucky now because both constructors have the same zero count
    # of arguments.
    # If the things change, such oneliner must be refactored.
    publisher: Publisher = types[name]()
    ctx.obj['result'] = AppCtx(payload=payload,
                               type=message_type,
                               publisher=publisher)
    return ctx.obj


def main():
    _setup_logging()
    try:
        raw_ctx = parse_opts(args=sys.argv[1:],
                             standalone_mode=False,
                             obj={})
        app_context = raw_ctx['result']
        pub = app_context.publisher
        offset = pub.publish(app_context.type, app_context.payload)
        logging.info('Written to epoch: %s', offset)

    except Exception:
        logging.exception('Exiting with failure')
