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
@click.argument('queue',
                type=click.Choice(['eq', 'bq'], case_sensitive=False),
                required=True)
@click.argument('type', type=str, required=True)
@click.argument('payload', type=str, required=True)
@click.pass_context
def parse_opts(ctx, queue: str, type: str, payload: str):
    """Send entry to target queue.

    \b
    QUEUE   Name of the target queue. Supported values: "eq" (Event Queue), "bq" (Broadcast Queue).
    TYPE    Type of the entry.
    PAYLOAD Entry payload encoded as JSON value.
    """
    ctx.ensure_object(dict)
    name = queue.lower()
    types = {'eq': EQPublisher, 'bq': BQPublisher}

    # We're lucky now because both constructors have the same zero count
    # of arguments.
    # If the things change, such oneliner must be refactored.
    publisher: Publisher = types[name]()
    ctx.obj['result'] = AppCtx(payload=payload,
                               type=type,
                               publisher=publisher)
    return ctx.obj


def main():
    _setup_logging()
    try:
        raw_ctx = parse_opts(args=sys.argv[1:],
                             standalone_mode=False,
                             obj={})
        if type(raw_ctx) is not dict:
            exit(1)
        app_context = raw_ctx['result']
        pub = app_context.publisher
        offset = pub.publish(app_context.type, app_context.payload)
        logging.info('Written to epoch: %s', offset)
    except Exception:
        logging.exception('Exiting with failure')
