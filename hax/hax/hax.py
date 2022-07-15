#!/usr/bin/env python3

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

import logging
import re
import signal
from typing import List, NamedTuple

import inject

from hax.common import HaxGlobalState, di_configuration
from hax.filestats import FsStatsUpdater
from hax.ha import create_ha_thread
from hax.handler import ConsumerThread
from hax.log import setup_logging
from hax.motr import Motr
from hax.motr.delivery import DeliveryHerald
from hax.motr.ffi import HaxFFI
from hax.motr.planner import WorkPlanner
from hax.motr.rconfc import RconfcStarter
from hax.server import ServerRunner
from hax.types import Fid, Profile, StoppableThread
from hax.util import ConsulUtil, repeat_if_fails


__all__ = ['main']

HL_Fids = NamedTuple('HL_Fids', [('hax_ep', str), ('hax_fid', Fid),
                                 ('ha_fid', Fid), ('profiles', List[Profile])])

LOG = logging.getLogger('hax')


def _run_thread(thread: StoppableThread) -> StoppableThread:
    thread.start()
    return thread


def _run_qconsumer_thread(planner: WorkPlanner, motr: Motr,
                          herald: DeliveryHerald, consul: ConsulUtil,
                          idx: int) -> StoppableThread:
    return _run_thread(ConsumerThread(planner, motr, herald, consul, idx))


def _run_stats_updater_thread(motr: Motr,
                              consul_util: ConsulUtil) -> StoppableThread:
    return _run_thread(FsStatsUpdater(motr, consul_util, interval_sec=30))


@repeat_if_fails()
def _remove_stale_session(util: ConsulUtil) -> None:
    '''Destroys a stale RC leader session if it exists or does nothing otherwise.

    An RC leader session may survive 'hctl shutdown'. In such a case 'leader'
    key will contain a garbage value 'elect2805' but the session will be alive
    and thus RC leader will not be re-elected.
    '''
    if not util.kv.kv_get_raw('leader'):
        # No leader key means that there can be no stale RC leader session for
        # sure. We're starting for the first time against a fresh Consul KV.
        return

    sess = util.get_leader_session_no_wait()
    # We might face situation where we have stale session such that we have
    # 'session' present but 'value' is not present for leader key.
    # In such situation we need to destroy the session so that RC re-election
    # can be triggered automatically
    if util.is_leader_value_present_for_session():
        node = util.get_leader_node()
        if re.match(r'^elect[\d]+$', node):
            LOG.debug(
                'Stale leader session found: RC leader session %s is '
                'found while the leader node seems to be '
                'stub: %s', sess, node)
            util.destroy_session(sess)
            LOG.debug('Stale session %s destroyed '
                      'to enable RC re-election', sess)
    else:
        util.destroy_session(sess)
        LOG.debug('Stale session %s destroyed to enable RC re-election', sess)


@repeat_if_fails()
def _get_motr_fids(util: ConsulUtil) -> HL_Fids:
    hax_ep: str = util.get_hax_endpoint()
    hax_fid: Fid = util.get_hax_fid()
    ha_fid: Fid = util.get_ha_fid()
    profiles = util.get_profiles()
    if not profiles:
        raise RuntimeError('Configuration error: no profile '
                           'is found in Consul KV')
    return HL_Fids(hax_ep, hax_fid, ha_fid, profiles)


def _run_rconfc_starter_thread(motr: Motr,
                               consul_util: ConsulUtil) -> RconfcStarter:
    rconfc_starter = RconfcStarter(motr, consul_util)
    rconfc_starter.start()
    return rconfc_starter


def main():
    # Note: no logging must happen before this call.
    # Otherwise the log configuration will not apply.
    setup_logging()
    inject.configure(di_configuration)

    state = inject.instance(HaxGlobalState)

    # [KN] The elements in the work planner will appear if
    # 1. A callback is invoked from ha_link (this will happen in a motr
    #    thread which must be free ASAP)
    # 2. A new HA notification has come form Consul via HTTP
    # [KN] The messages are consumed by Python threads created by
    # _run_qconsumer_thread function.
    #
    # [KN] Note: The server is launched in the main thread.
    planner = WorkPlanner()

    def handle_signal(sig, frame):
        state.set_stopping()
        planner.shutdown()

    # This is necessary to allow hax to exit early if Consul is not available
    # (otherwise _get_motr_fids() may be retrying forever even if the hax
    # process needs to shutdown).
    signal.signal(signal.SIGINT, handle_signal)

    util: ConsulUtil = ConsulUtil()
    # Avoid removing session on hax start as this will happen
    # on every node, thus leader election will keep re-triggering
    # until the final hax node starts, this will delay further
    # bootstrapping operations.
    _remove_stale_session(util)
    cfg: HL_Fids = _get_motr_fids(util)

    LOG.info('Welcome to HaX')
    LOG.info(f'Setting up ha_link interface with the options as follows: '
             f'hax fid = {cfg.hax_fid}, hax endpoint = {cfg.hax_ep}, '
             f'HA fid = {cfg.ha_fid}')
    ffi = HaxFFI()
    herald = DeliveryHerald()
    motr = Motr(planner=planner, ffi=ffi, herald=herald, consul_util=util)

    # Note that consumer thread must be started before we invoke motr.start(..)
    # Reason: hax process will send entrypoint request and somebody needs
    # to reply it.

    # TODO make the number of threads configurable
    consumer_threads = [
        _run_qconsumer_thread(planner, motr, herald,
                              util, i) for i in range(32)
    ]

    try:
        # [KN] We use just the first profile for Spiel API for now.
        motr.start(cfg.hax_ep,
                   process=cfg.hax_fid,
                   ha_service=cfg.ha_fid,
                   profile=cfg.profiles[0])
        LOG.info('Motr API has been started')
        rconfc_starter = _run_rconfc_starter_thread(motr, consul_util=util)

        stats_updater = _run_stats_updater_thread(motr, consul_util=util)
        event_poller = _run_thread(create_ha_thread(planner, util))
        # [KN] This is a blocking call. It will work until the program is
        # terminated by signal

        server = ServerRunner(planner,
                              herald,
                              consul_util=util,
                              hax_state=state)
        server.run(threads_to_wait=[
            *consumer_threads, stats_updater, rconfc_starter, event_poller
        ])
    except Exception:
        LOG.exception('Exiting due to an exception')
    finally:
        motr.fini()


if __name__ == '__main__':
    main()
