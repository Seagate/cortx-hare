# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#

import asyncio
import logging
from queue import Queue
from typing import Any, Dict, List

from aiohttp import web
from aiohttp.web_response import json_response

from hax.message import BroadcastHAStates
from hax.queue import BQProcessor
from hax.queue.offset import InboxFilter, OffsetStorage
from hax.types import HAState, StoppableThread
from hax.util import create_process_fid


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


def process_bq_update(inbox_filter: InboxFilter, processor: BQProcessor):
    async def _process(request):
        data = await request.json()

        def fn():
            messages = inbox_filter.prepare(data)
            if not messages:
                return
            processor.process(messages)
            last_epoch = messages[-1][0]
            inbox_filter.offset_mgr.mark_last_read(last_epoch)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, fn)

        return web.Response()

    return _process


def run_server(
    queue: Queue,
    threads_to_wait: List[StoppableThread] = [],
    port=8008,
):
    # Bind to ANY interface so scripts can use localhost to send requests
    # FIXME: This introduces security related concerns since hax becomes
    # available from network.
    addr = '0.0.0.0'
    inbox_filter = InboxFilter(
        OffsetStorage(addr, key_prefix='queue-offsets/bq'))

    app = web.Application()
    app.add_routes([
        web.get('/', hello_reply),
        web.post('/', process_ha_states(queue)),
        web.post('/watcher/bq', process_bq_update(inbox_filter,
                                                  BQProcessor(queue)))
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
