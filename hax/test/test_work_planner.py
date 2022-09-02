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
import time
import unittest
from queue import Queue
from threading import Condition, Thread
from typing import Any, List
from unittest.mock import Mock

from hax.log import TRACE
from hax.message import (BaseMessage, BroadcastHAStates, Die,
                         EntrypointRequest,
                         HaNvecGetEvent, ProcessEvent)
from hax.motr.planner import WorkPlanner, State
from hax.motr.util import LinkedList
from hax.types import Fid, Uint128, ConfHaProcess

LOG = logging.getLogger('hax')


class ThreadTracker:
    def __init__(self):
        self.lock = Condition()
        self.data = []

    def log(self, cmd: BaseMessage):
        with self.lock:
            self.data.append(self._extract_trace(cmd))

    def get_tracks(self) -> List[Any]:
        with self.lock:
            return self.data

    def _extract_trace(self, cmd: BaseMessage) -> Any:
        raise RuntimeError()


class GroupTracker(ThreadTracker):
    def _extract_trace(self, cmd: BaseMessage):
        return cmd.group


class TimeTracker(ThreadTracker):
    def _extract_trace(self, cmd):
        return (cmd, time.time())


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


def process_event():
    return ProcessEvent(
               ConfHaProcess(chp_event=0,
                             chp_type=0,
                             chp_pid=0,
                             fid=Fid(0, 0)))


class TestMessageOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # It seems like when unittest is invoked from setup.py,
        # some default logging configuration is already applied;
        # invoking setup_logging() will make the log messages to appear twice.
        logging.addLevelName(TRACE, 'TRACE')
        logging.getLogger('hax').setLevel(TRACE)

    def test_entrypoint_executed_asap(self):
        planner = WorkPlanner()

        a = planner._assign_group
        self.assertEqual(
            [0, 1, 0],
            [a(i)[0].group
             for i in [broadcast(), broadcast(),
                       entrypoint()]])

    def test_broadcast_does_not_start_new_group(self):
        planner = WorkPlanner()

        assign = planner._assign_group

        msgs = [
            assign(broadcast()),
            assign(broadcast()),
            assign(broadcast()),
            assign(nvec_get())
        ]
        self.assertEqual([0, 1, 2, 0], [m.group for (m, _) in msgs])

    def test_group_id_cycled(self):
        def my_state():
            return State(next_group_id=99999,
                         active_commands=LinkedList(),
                         active_meta={},
                         current_group_id=99999,
                         next_group_commands=set(),
                         is_shutdown=False)

        planner = WorkPlanner(init_state_factory=my_state)
        assign = planner._assign_group

        msgs = [
            assign(broadcast()),
            assign(broadcast()),
            assign(broadcast()),
            assign(broadcast()),
        ]
        self.assertEqual([99999, 10**5, 0, 1], [m.group for (m, _) in msgs])

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
        self.assertEqual([0, 0, 1, 0], [m.group for (m, _) in msgs_after_bc])
        self.assertEqual([0, 0, 2, 0], [m.group for (m, _) in msgs_after_ep])
        self.assertEqual([0, 0, 0, 0], [m.group for (m, _) in msgs_after_nvec])


class TestWorkPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # It seems like when unittest is invoked from setup.py,
        # some default logging configuration is already applied;
        # invoking setup_logging() will make the log messages to appear twice.
        logging.addLevelName(TRACE, 'TRACE')
        logging.getLogger('hax').setLevel(TRACE)

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
        for _ in range(10):
            planner.add_command(nvec_get())

        for _ in range(thread_count):
            planner.add_command(Die())

        def fn(planner: WorkPlanner, exc: Queue):
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received %s [group=%s]",
                            type(cmd), cmd.group)

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
                exc.put(e)

        excq = Queue(maxsize=thread_count)
        workers = [
            Thread(target=fn, args=(planner, excq)) for t in range(thread_count)
        ]
        for t in workers:
            t.start()

        for t in workers:
            t.join()
        # raises the first collected exception
        if excq.qsize() != 0:
            raise excq.get()
        groups_processed = tracker.get_tracks()
        self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], groups_processed)


    def test_entrypoint_request_processed_asap(self):
        planner = WorkPlanner()
        tracker = TimeTracker()
        thread_count = 4
        planner.add_command(broadcast())
        planner.add_command(broadcast())
        planner.add_command(broadcast())
        planner.add_command(entrypoint())

        for j in range(thread_count):
            planner.add_command(Die())

        excq = Queue(maxsize=thread_count)

        def fn(planner: WorkPlanner, exc: Queue):
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received %s [group=%s]",
                            type(cmd), cmd.group)
                    if isinstance(cmd, BroadcastHAStates):
                        time.sleep(1.5)

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
                exc.put(e)

        workers = [
            Thread(target=fn, args=(planner, excq)) for t in range(thread_count)
        ]
        for t in workers:
            t.start()

        for t in workers:
            t.join()
        # raises the first collected exception and test can be improved
        if excq.qsize() != 0:
            raise excq.get()
        tracks = tracker.get_tracks()
        cmd = tracks[0][0]
        self.assertTrue(isinstance(cmd, EntrypointRequest))

    def test_workers_not_blocked_by_future_work(self):
        planner = WorkPlanner()
        tracker = TimeTracker()
        thread_count = 2
        # We add way more commands than we have workers now
        for _ in range(8):
            planner.add_command(broadcast())

        planner.add_command(entrypoint())

        for _ in range(thread_count):
            planner.add_command(Die())

        exc = None

        def fn(planner: WorkPlanner):
            nonlocal exc
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received %s [group=%s]",
                            type(cmd), cmd.group)

                    if isinstance(cmd, BroadcastHAStates):
                        time.sleep(1)

                    if isinstance(cmd, EntrypointRequest):
                        planner.shutdown()

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

        t0 = time.time()
        for t in workers:
            t.start()

        for t in workers:
            t.join()
        if exc:
            raise exc
        tracks = tracker.get_tracks()

        _, (_, ts) = self.find(tracks,
                             lambda a: isinstance(a[0], EntrypointRequest),
                             'EntrypointRequest not processed')
        self.assertTrue(ts - t0 < 3)
        self.assertTrue(len(tracks) < 4)

    def find(self, collection, find_by, msg_if_fail=''):
        for (i, elem) in enumerate(collection):
            if find_by(elem):
                return (i, elem)
        raise RuntimeError(f'Not found: {msg_if_fail}')

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
            planner.add_command(nvec_get())

        for j in range(thread_count):
            planner.add_command(Die())

        exc = None

        def fn(planner: WorkPlanner):
            nonlocal exc
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received %s [group=%s]",
                            type(cmd), cmd.group)

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
        self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], groups_processed)

    def test_no_hang_when_group_id_cycled(self):
        planner = WorkPlanner()

        def my_state():
            return State(next_group_id=99999,
                         active_commands=LinkedList(),
                         active_meta={},
                         current_group_id=99999,
                         next_group_commands=set(),
                         is_shutdown=False)

        planner = WorkPlanner(init_state_factory=my_state)

        tracker = GroupTracker()
        thread_count = 1
        for i in range(10):
            planner.add_command(broadcast())

        for j in range(thread_count):
            planner.add_command(Die())

        exc = None

        def fn(planner: WorkPlanner):
            nonlocal exc
            try:
                while True:
                    LOG.log(TRACE, "Requesting for a work")
                    # import pudb.remote
                    # pudb.remote.set_trace(term_size=(120, 40), port=9998)
                    cmd = planner.get_next_command()
                    LOG.log(TRACE, "The command is received %s [group=%s]",
                            type(cmd), cmd.group)

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
        self.assertEqual([99999, 10**5, 0, 1, 2, 3, 4,
                          5, 6, 7], groups_processed)

