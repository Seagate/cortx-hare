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
import base64
import logging
import os
import sys
from json.decoder import JSONDecodeError
from queue import Queue
from typing import Any, Callable, Dict, List, Type, Union

from aiohttp import web
from aiohttp.web import HTTPError, HTTPNotFound
from aiohttp.web_response import json_response
from helper.exec import Executor, Program

from hax.common import HaxGlobalState
from hax.message import (BaseMessage, BroadcastHAStates, SnsDiskAttach,
                         SnsDiskDetach, SnsRebalancePause, SnsRebalanceResume,
                         SnsRebalanceStart, SnsRebalanceStatus,
                         SnsRebalanceStop, SnsRepairPause, SnsRepairResume,
                         SnsRepairStart, SnsRepairStatus, SnsRepairStop)
from hax.motr.delivery import DeliveryHerald
from hax.motr.planner import WorkPlanner
from hax.queue import BQProcessor
from hax.queue.confobjutil import ConfObjUtil
from hax.queue.offset import InboxFilter, OffsetStorage
from hax.rc import Synchronizer
from hax.types import Fid, HAState, ServiceHealth, StoppableThread
from hax.util import ConsulUtil, create_process_fid, dump_json

LOG = logging.getLogger('hax')


async def hello_reply(request):
    return json_response(text="I'm alive! Sincerely, HaX")


def get_python_env():
    path = os.environ['PATH']
    py_path = ':'.join(sys.path)
    if 'PYTHONPATH' in os.environ:
        env_var = os.environ['PYTHONPATH']
        py_path = f'{env_var}:{py_path}'
    env = {
        'PATH':
        ':'.join([
            '/opt/seagate/cortx/hare/bin',
            '/opt/seagate/cortx/hare/libexec', path
        ]),
        'PYTHONPATH':
        py_path
    }
    return env


def hctl_stat(request):
    """This function calls the hare-status script from the hax-server in order
    to provide CSM with an endpoint to get the hctl status --json data.
    """
    exec = Executor()
    env = get_python_env()
    result = exec.run(Program(["/opt/seagate/cortx/hare/libexec/hare-status",
                      "--json"]), env=env)
    return json_response(text=result)


def to_ha_states(data: Any, consul_util: ConsulUtil) -> List[HAState]:
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


def process_ha_states(planner: WorkPlanner, consul_util: ConsulUtil):
    async def _process(request):
        data = await request.json()

        loop = asyncio.get_event_loop()

        def fn():
            # import pudb.remote
            # pudb.remote.set_trace(term_size=(80, 40), port=9998)
            LOG.debug('Service health from Consul: %s', data)
            planner.add_command(
                BroadcastHAStates(states=to_ha_states(data, consul_util),
                                  reply_to=None))

        # Note that planner.add_command is potentially a blocking call
        await loop.run_in_executor(None, fn)
        return web.Response()

    return _process


def process_sns_operation(planner: WorkPlanner):
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
        await loop.run_in_executor(None, lambda: planner.add_command(message))
        return web.Response()

    return _process


def get_sns_status(planner: WorkPlanner,
                   status_type: Union[Type[SnsRepairStatus],
                                      Type[SnsRebalanceStatus]]):
    def fn(request):
        queue: Queue = Queue(1)
        planner.add_command(
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


def process_leader_change(my_node: str, rc_synch: Synchronizer):
    async def _process_leader(request):
        data = await request.json()
        if not data:
            return web.Response()

        def fn():
            # session_id = data['Session']
            leader_node = base64.b64decode(data['Value']).decode()
            LOG.debug('XXX RC updated: %s', data)
            rc_synch.set_leader(leader_node == my_node)

            return web.Response()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, fn)

        return web.Response()

    return _process_leader


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


class ServerRunner:
    def __init__(
        self,
        planner: WorkPlanner,
        herald: DeliveryHerald,
        consul_util: ConsulUtil,
        hax_state: HaxGlobalState,
        rc_synch: Synchronizer
    ):
        self.consul_util = consul_util
        self.herald = herald
        self.planner = planner
        self.hax_state = hax_state
        self.rc_synch = rc_synch

    def _create_server(self) -> web.Application:
        return web.Application(middlewares=[encode_exception])

    def _get_my_hostname(self) -> str:
        return self.consul_util.get_hax_ip_address()

    def _configure(self) -> None:
        # We can't use broad 0.0.0.0 IP address to make it possible to run
        # multiple hax instances at the same machine (i.e. in failover
        # situation).
        # Instead, every hax will use a private IP only.
        node_address = self._get_my_hostname()

        # Note that bq-delivered mechanism must use a unique node name rather
        # than broad '0.0.0.0' that doesn't identify the node from outside.
        inbox_filter = InboxFilter(
            OffsetStorage(node_address,
                          key_prefix='bq-delivered',
                          kv=self.consul_util.kv))

        conf_obj = ConfObjUtil(self.consul_util)
        planner = self.planner
        herald = self.herald
        consul_util = self.consul_util
        synch = self.rc_synch
        my_node = consul_util.get_local_nodename()

        app = self._create_server()
        app.add_routes([
            web.get('/', hello_reply),
            web.get('/cluster/status', hctl_stat),
            web.post('/', process_ha_states(planner, consul_util)),
            web.post(
                '/watcher/bq',
                process_bq_update(inbox_filter,
                                  BQProcessor(planner, herald, conf_obj))),
            web.post(
                '/watcher/leader',
                process_leader_change(my_node, synch)),
            web.post('/api/v1/sns/{operation}',
                     process_sns_operation(planner)),
            web.get('/api/v1/sns/repair-status',
                    get_sns_status(planner, SnsRepairStatus)),
            web.get('/api/v1/sns/rebalance-status',
                    get_sns_status(planner, SnsRebalanceStatus)),
        ])
        self.app = app

    def _start(self, web_address: str, port: int) -> None:
        web.run_app(self.app, host=web_address, port=port)

    def run(
        self,
        threads_to_wait: List[StoppableThread] = [],
        port=8008,
    ):
        self._configure()
        web_address = self._get_my_hostname()
        LOG.info(f'Starting HTTP server at {web_address}:{port} ...')
        try:
            self._start(web_address, port)
            LOG.debug('Server stopped normally')
        finally:
            self.hax_state.set_stopping()
            LOG.debug('Stopping the threads')
            self.planner.shutdown()
            for thread in threads_to_wait:
                thread.stop()
            for thread in threads_to_wait:
                thread.join()

            LOG.info('The http server has stopped')
