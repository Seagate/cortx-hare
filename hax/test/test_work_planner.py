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

# flake8: noqa
import logging
import sys
import time
import unittest
from threading import Condition, Thread
from time import sleep
from typing import List
from unittest.mock import Mock

from hax.exception import NotDelivered
from hax.log import TRACE
from hax.message import (BaseMessage, BroadcastHAStates, Die,
                         EntrypointRequest, FirstEntrypointRequest,
                         HaNvecGetEvent)
from hax.motr.planner import WorkPlanner
from hax.types import Fid, HaLinkMessagePromise, MessageId, Uint128

LOG = logging.getLogger('hax')


class GroupTracker:
    def __init__(self):
        self.lock = Condition()
        self.data = []

    def log(self, cmd: BaseMessage):
        with self.lock:
            self.data.append(cmd.group)

    def get_tracks(self) -> List[BaseMessage]:
        with self.lock:
            return list(self.data)


def entrypoint():
    return EntrypointRequest(reply_context='test',
                             req_id=Uint128(1, 2),
                             remote_rpc_endpoint='endpoint',
                             process_fid=Fid(1, 2),
                             git_rev='HEAD',
                             pid=123,
                             is_first_request=False)


def broadcast():
    return BroadcastHAStates(states=[], reply_to=None)


def nvec_get():
    return HaNvecGetEvent(hax_msg=1, nvec=[])


class TestMessageOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # It seems like when unittest is invoked from setup.py,
        # some default logging configuration is already applied;
        # invoking setup_logging() will make the log messages to appear twice.
        logging.addLevelName(TRACE, 'TRACE')
        logging.getLogger('hax').setLevel(TRACE)

    def test_entrypoint_requests_share_same_group(self):
        planner = WorkPlanner()
        ep1 = entrypoint()
        ep2 = entrypoint()

        ep1 = planner._assign_group(ep1)
        ep2 = planner._assign_group(ep2)
        self.assertEqual([0, 0], [ep1.group, ep2.group])

    def test_entrypoint_not_paralleled_with_broadcast(self):
        planner = WorkPlanner()
        bcast = broadcast()
        ep1 = entrypoint()

        bcast = planner._assign_group(bcast)
        ep1 = planner._assign_group(ep1)
        self.assertEqual([0, 1], [bcast.group, ep1.group])

    def test_broadcast_starts_new_group(self):
        planner = WorkPlanner()

        assign = planner._assign_group

        msgs = [
            assign(broadcast()),
            assign(broadcast()),
            assign(broadcast()),
            assign(entrypoint())
        ]
        self.assertEqual([0, 1, 2, 3], [m.group for m in msgs])

    def test_ha_nvec_get_shares_group_always(self):
        planner = WorkPlanner()

        assign = planner._assign_group

        msgs_after_bc = [
            assign(broadcast()),
            assign(nvec_get()),
            assign(broadcast()),
            assign(entrypoint())
        ]
        msgs_after_ep = [
            assign(entrypoint()),
            assign(nvec_get()),
            assign(broadcast()),
            assign(entrypoint())
        ]
        msgs_after_nvec = [
            assign(entrypoint()),
            assign(nvec_get()),
            assign(nvec_get()),
            assign(entrypoint())
        ]
        self.assertEqual([0, 0, 1, 2], [m.group for m in msgs_after_bc])
        self.assertEqual([2, 2, 3, 4], [m.group for m in msgs_after_ep])
        self.assertEqual([4, 4, 4, 4], [m.group for m in msgs_after_nvec])


class TestWorkPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # It seems like when unittest is invoked from setup.py,
        # some default logging configuration is already applied;
        # invoking setup_logging() will make the log messages to appear twice.
        logging.addLevelName(TRACE, 'TRACE')
        logging.getLogger('hax').setLevel(TRACE)

    def test_parallelism_is_possible(self):
        planner = WorkPlanner()
        for i in range(40):
            planner.add_command(entrypoint())

        for j in range(4):
            planner.add_command(Die())

        exc = None

        def fn(planner: WorkPlanner):
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received")
                    if isinstance(cmd, Die):
                        LOG.log(TRACE,
                                "Poison pill is received - exiting. Bye!")
                        break

                    planner.ensure_allowed(cmd)
                    LOG.log(TRACE, "I'm allowed to work on it!")
                    sleep(0.5)
                    LOG.log(TRACE, "The job is done, notifying the planner")
                    planner.notify_finished(cmd)
                    LOG.log(TRACE, "Notified. ")

            except Exception as e:
                LOG.exception('*** ERROR ***')
                exc = e

        workers = [Thread(target=fn, args=(planner, )) for t in range(4)]
        time_1 = time.time()
        for t in workers:
            t.start()

        for t in workers:
            t.join()
        time_2 = time.time()
        logging.info('Processing time %s', time_2 - time_1)
        if exc:
            raise exc
        self.assertTrue(planner.is_empty(), 'Not all commands were read out')
        # Every thread sleeps for 500ms. 40 commands * 0.5 gives 20 seconds if the
        # commands executed sequentially
        self.assertLess(time_2 - time_1, 19, 'Suspiciously slow')

    def test_groups_processed_sequentially_12_threads(self):
        planner = WorkPlanner()
        group_idx = 0

        def ret_values(cmd: BaseMessage) -> bool:
            nonlocal group_idx
            # We don't care about the group distribution logic
            # in this test. Instead, we concentrate how different group
            # numbers are processed by the workers and the order
            # in which they are allowed to process the messages.
            #
            # _assign_group is invoked under a lock acquired, so this
            # increment is thread-safe.
            values = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
            ret = bool(values[group_idx])
            group_idx += 1
            return ret

        setattr(planner, '_should_increase_group',
                Mock(side_effect=ret_values))
        tracker = GroupTracker()
        thread_count = 12
        for i in range(10):
            planner.add_command(entrypoint())

        for j in range(thread_count):
            planner.add_command(Die())

        exc = None

        def fn(planner: WorkPlanner):
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received %s [group=%s]",
                            type(cmd), cmd.group)

                    planner.ensure_allowed(cmd)
                    LOG.log(TRACE, "I'm allowed to work on it!")
                    if isinstance(cmd, Die):
                        LOG.log(TRACE,
                                "Poison pill is received - exiting. Bye!")
                        planner.notify_finished(cmd)
                        break
                    tracker.log(cmd)
                    LOG.log(TRACE, "The job is done, notifying the planner")
                    planner.notify_finished(cmd)
                    LOG.log(TRACE, "Notified. ")

            except Exception as e:
                LOG.exception('*** ERROR ***')
                exc = e

        workers = [
            Thread(target=fn, args=(planner, )) for t in range(thread_count)
        ]
        for t in workers:
            t.start()

        for t in workers:
            t.join()
        if exc:
            raise exc
        groups_processed = tracker.get_tracks()
        self.assertEqual([0, 1, 1, 2, 2, 3, 3, 4, 4, 5], groups_processed)

    def test_groups_processed_sequentially_4_threads(self):
        planner = WorkPlanner()
        group_idx = 0

        def ret_values(cmd: BaseMessage) -> bool:
            nonlocal group_idx
            # We don't care about the group distribution logic
            # in this test. Instead, we concentrate how different group
            # numbers are processed by the workers and the order
            # in which they are allowed to process the messages.
            #
            # _assign_group is invoked under a lock acquired, so this
            # increment is thread-safe.
            values = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
            ret = bool(values[group_idx])
            group_idx += 1
            return ret

        setattr(planner, '_should_increase_group',
                Mock(side_effect=ret_values))
        tracker = GroupTracker()
        thread_count = 4
        for i in range(10):
            planner.add_command(entrypoint())

        for j in range(thread_count):
            planner.add_command(Die())

        exc = None

        def fn(planner: WorkPlanner):
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received %s [group=%s]",
                            type(cmd), cmd.group)

                    planner.ensure_allowed(cmd)
                    LOG.log(TRACE, "I'm allowed to work on it!")
                    if isinstance(cmd, Die):
                        LOG.log(TRACE,
                                "Poison pill is received - exiting. Bye!")
                        planner.notify_finished(cmd)
                        break
                    tracker.log(cmd)
                    LOG.log(TRACE, "The job is done, notifying the planner")
                    planner.notify_finished(cmd)
                    LOG.log(TRACE, "Notified. ")

            except Exception as e:
                LOG.exception('*** ERROR ***')
                exc = e

        workers = [
            Thread(target=fn, args=(planner, )) for t in range(thread_count)
        ]
        for t in workers:
            t.start()

        for t in workers:
            t.join()
        if exc:
            raise exc
        groups_processed = tracker.get_tracks()
        self.assertEqual([0, 1, 1, 2, 2, 3, 3, 4, 4, 5], groups_processed)
