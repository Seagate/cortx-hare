import asyncio
import logging
from queue import Queue
from typing import Any, Dict, List

from aiohttp import web
from aiohttp.web_response import json_response

from hax.message import BroadcastHAStates
from hax.queue.offset import InboxFilter, OffsetStorage
from hax.types import HAState, StoppableThread
from hax.util import ConsulUtil, create_process_fid


async def hello_reply(request):
    return json_response(text="I'm alive! Sincerely, HaX")


def to_ha_states(data: Any) -> List[HAState]:
    """Converts a dictionary, obtained from JSON data, into a list of
    HA states.

    Format of an HA state: HAState(fid= <service fid>, status= <state>),
    where <state> is either 'online' or 'offline'.
    """
    if not data:
        return []

    def get_status(checks: List[Dict[str, Any]]) -> str:
        ok = all(x.get('Status') == 'passing' for x in checks)
        return 'online' if ok else 'offline'

    return [
        HAState(fid=create_process_fid(int(t['Service']['ID'])),
                status=get_status(t['Checks'])) for t in data
    ]


def process_ha_states(queue: Queue):
    async def _process(request):
        data = await request.json()

        loop = asyncio.get_event_loop()
        # Note that queue.put is potentially a blocking call
        await loop.run_in_executor(
            None, lambda: queue.put(BroadcastHAStates(to_ha_states(data))))
        return web.Response()

    return _process


def process_bq_update(inbox_filter: InboxFilter):
    async def _process(request):
        data = await request.json()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None,
                                            lambda: inbox_filter.process(data))
        logging.info('XXX HERE - BQ')
        logging.info('XXX Received: %s', result)
        if result:
            last_epoch = result[-1][0]
            await loop.run_in_executor(
                None,
                lambda: inbox_filter.offset_mgr.mark_last_read(last_epoch))

        return web.Response()

    return _process


def run_server(
    queue: Queue,
    threads_to_wait: List[StoppableThread] = [],
    port=8008,
):
    addr = ConsulUtil().get_hax_ip_address()
    inbox_filter = InboxFilter(
        OffsetStorage(addr, key_prefix='queue-offsets/bq'))

    app = web.Application()
    app.add_routes([
        web.get('/', hello_reply),
        web.post('/', process_ha_states(queue)),
        web.post('/watcher/bq', process_bq_update(inbox_filter))
    ])
    logging.info(f'Starting HTTP server at {addr}:{port} ...')
    try:
        web.run_app(app, host=addr, port=port)
        logging.debug('Server stopped normally')
    finally:
        logging.debug('Stopping the threads')
        for thread in threads_to_wait:
            thread.stop()
        for thread in threads_to_wait:
            thread.join()

        logging.info('The http server has stopped')
