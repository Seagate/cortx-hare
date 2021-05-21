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
from collections import deque
from dataclasses import dataclass
from threading import Condition
from typing import Callable, Deque, Optional, Type

from hax.log import TRACE
from hax.message import (AnyEntrypointRequest, BaseMessage, BroadcastHAStates,
                         Die, HaNvecGetEvent, SnsOperation)
from hax.motr.util import LinkedSet

LOG = logging.getLogger('hax')
MAX_GROUP_ID = 100000

__all__ = ['WorkPlanner']


@dataclass
class State:
    #
    # group being executed currently
    current_group_id: int
    #
    # group that is being populated by next add_command() invocation
    next_group_id: int
    #
    # commands that are being processed now
    active_commands: LinkedSet[BaseMessage]
    taken_commands: LinkedSet[BaseMessage]
    next_group_commands: LinkedSet[Type[BaseMessage]]
    is_shutdown: bool


class WorkPlanner:
    """
    Thread synchronizing block that is used as a work planner for Motr-aware
    threads (see ConsumerThread). This synchronizing primitive guarantees that

    1. The messages can be processed by an arbitrary number of ConsumerThread
       threads.

    2. The parallelism doesn't break semantics (some messages can be processed
       in parallel to others, while some other not; the ConsumerThread's don't
       need to worry about that).
    """
    def __init__(self,
                 init_state_factory: Optional[Callable[[], State]] = None):
        fn = init_state_factory or self._create_initial_state

        self.state = fn()
        self.backlog: Deque[BaseMessage] = deque()
        self.b_lock = Condition()

    def is_empty(self) -> bool:
        """Checks whether the backlog is empty. Blocking call."""
        with self.b_lock:
            return not self.backlog

    def add_command(self, command: BaseMessage) -> None:
        LOG.log(TRACE, '[WP]Before add_command: %s', command)
        with self.b_lock:
            cmd = self._assign_group(command)
            LOG.log(TRACE, '[WP]Cmd %s is added. Current state: %s', cmd,
                    self.state)
            self.backlog.append(cmd)
            # Some threads may be waiting because of an empty backlog - let's
            # notify them
            self.b_lock.notifyAll()

    def _create_initial_state(self) -> State:
        return State(next_group_id=0,
                     active_commands=LinkedSet(),
                     taken_commands=LinkedSet(),
                     current_group_id=0,
                     next_group_commands=LinkedSet(),
                     is_shutdown=False)

    def _create_poison(self) -> BaseMessage:
        cmd = Die()
        cmd.group = self.state.current_group_id
        return cmd

    def get_next_command(self) -> BaseMessage:
        while True:
            LOG.log(TRACE, '[WP]Trying to get new command')
            with self.b_lock:
                if self.state.is_shutdown:
                    return self._create_poison()
                if self.backlog:
                    cmd = self.backlog.popleft()
                    LOG.log(TRACE, '[WP]Cmd %s taken!', cmd)
                    self.state.taken_commands.add(cmd)
                    return cmd
                LOG.log(TRACE, '[WP]Blocking thread: no commands in backlog')
                self.b_lock.wait()

    def shutdown(self):
        with self.b_lock:
            LOG.debug('WorkPlanner is shutting down')
            self.state.is_shutdown = True
            self.b_lock.notifyAll()

    def ensure_allowed(self, command: BaseMessage) -> BaseMessage:
        def is_current(cmd: BaseMessage, st: State) -> bool:
            return cmd.group == st.current_group_id

        while True:
            with self.b_lock:
                state = self.state
                if state.is_shutdown:
                    return self._create_poison()
                if is_current(command, state):
                    state.taken_commands.remove(command)
                    state.active_commands.add(command)
                    return command
                LOG.log(TRACE, '[WP]Cmd %s not allowed for now.'
                        ' Current state: %s', command, self.state)
                self.b_lock.wait()

    def _get_increased_group(self, current: int) -> int:
        """ Returns the next valid group_id number by the given current value.
            Performs no side effects.
        """
        new_value = current + 1
        # In Python, every int uses an arbitrary-precision maths. In other
        # words, if an int value becomes greater than 4 bytes can store, no
        # overflow will happen. Instead, the variable will use more and more
        # additional chunks of memory. That's why group id should be wrapped
        # back to zero manually.
        if new_value > MAX_GROUP_ID:
            new_value = 0
        return new_value

    def _inc_group(self):
        state = self.state
        cur_group_id = state.current_group_id
        change_next_group = state.next_group_id == cur_group_id

        state.current_group_id = self._get_increased_group(cur_group_id)

        if change_next_group:
            state.next_group_id = state.current_group_id
            state.next_group_commands = LinkedSet()

    def notify_finished(self, command: BaseMessage) -> None:
        with self.b_lock:
            state = self.state
            state.active_commands.remove(command)
            LOG.log(TRACE, '[WP]Cmd %s removed. Current state: %s', command,
                    state)

            if state.active_commands:
                return
            for c in self.backlog:
                if c.group == state.current_group_id:
                    return
            for c in state.taken_commands:
                if c.group == state.current_group_id:
                    return
            # if we're here, command was the only one belonging to group
            self._inc_group()
            LOG.log(TRACE, '[WP]Active group changed to %s',
                    state.current_group_id)
            # The group changed, let's unblock those who are waiting for
            # this group
            self.b_lock.notifyAll()

    def _should_increase_group(self, cmd: BaseMessage) -> bool:
        def has(cmd_type: Type[BaseMessage]) -> bool:
            ''' Checks if the group being currently formed (i.e. next_group)
                contains a message of the given type.
            '''
            return cmd_type in self.state.next_group_commands

        if not self.state.next_group_commands:
            # current group is empty -> join it freely
            return False
        if isinstance(cmd, HaNvecGetEvent):
            # HaNvecGetEvent can be done in parallel to any other commands.
            # No need to form the new group for it.
            return False
        if isinstance(cmd, AnyEntrypointRequest):
            # if the current group has a BroadcastHAStates request,
            # then this entrypoint request should be placed to a next group.
            return has(BroadcastHAStates)
        if isinstance(cmd, BroadcastHAStates):
            return True

        if isinstance(cmd, SnsOperation):
            # Start new group if there is another SNS operation within the
            # current group.
            return has(SnsOperation)
        return False

    def _assign_group(self, cmd: BaseMessage) -> BaseMessage:
        ''' Sets the correct group_id to the command.
            Must be invoked with b_lock acquired.
        '''
        def join_group(cmd: BaseMessage) -> BaseMessage:
            cmd.group = self.state.next_group_id
            self.state.next_group_commands.add(type(cmd))
            return cmd

        def next_group() -> None:
            self.state.next_group_commands = LinkedSet()
            self.state.next_group_id = self._get_increased_group(
                self.state.next_group_id)

        if isinstance(cmd, Die):
            return join_group(cmd)

        if self._should_increase_group(cmd):
            next_group()

        return join_group(cmd)
