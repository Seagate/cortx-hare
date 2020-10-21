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
from json.decoder import JSONDecodeError
from queue import Queue
from typing import Any, Callable, Dict, List, Type, Union

from aiohttp import web
from aiohttp.web import HTTPError, HTTPNotFound
from aiohttp.web_response import json_response

from hax.message import (BaseMessage, BroadcastHAStates, SnsDiskAttach,
                         SnsDiskDetach, SnsRebalancePause, SnsRebalanceResume,
                         SnsRebalanceStart, SnsRebalanceStatus,
                         SnsRebalanceStop, SnsRepairPause, SnsRepairResume,
                         SnsRepairStart, SnsRepairStatus, SnsRepairStop)
from hax.motr.delivery import DeliveryHerald
from hax.queue import BQProcessor
from hax.queue.offset import InboxFilter, OffsetStorage
from hax.types import Fid, HAState, ServiceHealth, StoppableThread
from hax.util import ConsulUtil, create_process_fid, dump_json

LOG = logging.getLogger('hax')


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

    def get_status(checks: List[Dict[str, Any]]) -> ServiceHealth:
        ok = all(x.get('Status') == 'passing' for x in checks)
        return ServiceHealth.OK if ok else ServiceHealth.FAILED

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
            None, lambda: queue.put(
                BroadcastHAStates(states=to_ha_states(data), reply_to=None)))
        return web.Response()

    return _process


def process_sns_operation(queue: Queue):
    async def _process(request):
        op_name = request.match_info.get('operation')

        def create_handler(
            a_type: Callable[[Fid], BaseMessage]
        ) -> Callable[[Dict[str, Any]], BaseMessage]:
            def fn(data: Dict[str, Any]):
                fid = Fid.parse(data['fid'])
                return a_type(fid)

            return fn

        msg_factory = {
            'rebalance-start': create_handler(SnsRebalanceStart),
            'rebalance-stop': create_handler(SnsRebalanceStop),
            'rebalance-pause': create_handler(SnsRebalancePause),
            'rebalance-resume': create_handler(SnsRebalanceResume),
            'repair-start': create_handler(SnsRepairStart),
            'repair-stop': create_handler(SnsRepairStop),
            'repair-pause': create_handler(SnsRepairPause),
            'repair-resume': create_handler(SnsRepairResume),
            'disk-attach': create_handler(SnsDiskAttach),
            'disk-detach': create_handler(SnsDiskDetach),
        }

        LOG.debug(f'process_sns_operation: {op_name}')
        if op_name not in msg_factory:
            raise HTTPNotFound()
        data = await request.json()
        message = msg_factory[op_name](data)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: queue.put(message))
        return web.Response()

    return _process


def get_sns_status(motr_queue: Queue,
                   status_type: Union[Type[SnsRepairStatus],
                                      Type[SnsRebalanceStatus]]):
    def fn(request):
        queue = Queue(1)
        motr_queue.put(
            status_type(reply_to=queue,
                        fid=Fid.parse(request.query['pool_fid'])))
        return queue.get(timeout=10)

    async def _process(request):
        LOG.debug('%s with params: %s', request, request.query)
        loop = asyncio.get_event_loop()
        payload = await loop.run_in_executor(None, fn, request)
        return json_response(data=payload, dumps=dump_json)

    return _process


def process_bq_update(inbox_filter: InboxFilter, processor: BQProcessor):
    async def _process(request):
        data = await request.json()

        def fn():
            messages = inbox_filter.prepare(data)
            if not messages:
                return
            for i, msg in messages:
                processor.process((i, msg))
                # Mark the message as read ASAP since the process can
                # potentially die any time
                inbox_filter.offset_mgr.mark_last_read(i)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, fn)

        return web.Response()

    return _process


@web.middleware
async def encode_exception(request, handler):
    def error_response(e: Exception, code=500, reason=""):
        payload = {
            "status_code": code,
            "error_message": str(e),
            "error_type": e.__class__.__name__,
            "reason": reason
        }
        return json_response(data=payload, status=code)

    try:
        response = await handler(request)
        return response
    except HTTPError:
        raise
    except (JSONDecodeError, KeyError) as e:
        return error_response(e, code=400, reason="Bad JSON provided")
    except Exception as e:
        return error_response(e,
                              code=500,
                              reason="Unexpected error has happened")


def run_server(
    queue: Queue,
    herald: DeliveryHerald,
    threads_to_wait: List[StoppableThread] = [],
    port=8008,
):
    node_address = ConsulUtil().get_hax_ip_address()

    # We can't use broad 0.0.0.0 IP address to make it possible to run
    # multiple hax instances at the same machine (i.e. in failover situation).
    # Instead, every hax will use a private IP only.
    web_address = node_address

    # Note that bq-delivered mechanism must use a unique node name rather than
    # broad '0.0.0.0' that doesn't identify the node from outside.
    inbox_filter = InboxFilter(
        OffsetStorage(node_address, key_prefix='bq-delivered'))

    app = web.Application(middlewares=[encode_exception])
    app.add_routes([
        web.get('/', hello_reply),
        web.post('/', process_ha_states(queue)),
        web.post('/watcher/bq',
                 process_bq_update(inbox_filter, BQProcessor(queue, herald))),
        web.post('/api/v1/sns/{operation}', process_sns_operation(queue)),
        web.get('/api/v1/sns/repair-status',
                get_sns_status(queue, SnsRepairStatus)),
        web.get('/api/v1/sns/rebalance-status',
                get_sns_status(queue, SnsRebalanceStatus)),
    ])
    LOG.info(f'Starting HTTP server at {web_address}:{port} ...')
    try:
        web.run_app(app, host=web_address, port=port)
        LOG.debug('Server stopped normally')
    finally:
        LOG.debug('Stopping the threads')
        for thread in threads_to_wait:
            thread.stop()
        for thread in threads_to_wait:
            thread.join()

        LOG.info('The http server has stopped')
