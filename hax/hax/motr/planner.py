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
from typing import Deque, Set, Type

from hax.message import (AnyEntrypointRequest, BaseMessage, BroadcastHAStates,
                         HaNvecGetEvent, SnsOperation)

LOG = logging.getLogger('hax')

__all__ = ['WorkPlanner']


@dataclass
class State:
    current_group_id: int
    next_group_id: int
    active_commands: Set[BaseMessage]
    next_group_commands: Set[Type[BaseMessage]]


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
    def __init__(self):
        self.state = State(next_group_id=0,
                           active_commands=set(),
                           current_group_id=0,
                           next_group_commands=set())
        self.backlog: Deque[BaseMessage] = deque()
        self.b_lock = Condition()

    def add_command(self, command: BaseMessage) -> None:
        with self.b_lock:
            cmd = self._assign_group(command)
            self.backlog.append(cmd)
            # Some threads may be waiting because of an empty backlog - let's
            # notify them
            self.b_lock.notifyAll()

    def get_next_command(self) -> BaseMessage:
        # TODO think of is_stopped and shutdown procedure
        while True:
            with self.b_lock:
                if self.backlog:
                    return self.backlog.pop()
                self.b_lock.wait()

    def ensure_allowed(self, command: BaseMessage) -> None:
        def is_current(cmd: BaseMessage, st: State) -> bool:
            return cmd.group == st.current_group_id

        while True:
            with self.b_lock:
                state = self.state
                if is_current(command, state):
                    state.active_commands.add(command)
                    return
                self.b_lock.wait()

    def notify_finished(self, command: BaseMessage) -> None:
        with self.b_lock:
            state = self.state
            state.active_commands.remove(command)
            if state.active_commands:
                return
            for c in self.backlog:
                if c.group == command.group:
                    return
            # if we're here, command was the only one belonging to group
            state.current_group_id = state.next_group_id
            # The group changed, let's unblock those who are waiting for
            # this group
            self.b_lock.notifyAll()

    def _assign_group(self, cmd: BaseMessage) -> BaseMessage:
        ''' Sets the correct group_id to the command.
            Must be invoked with b_lock acquired.
        '''
        def has(cmd_type: Type[BaseMessage]) -> bool:
            ''' Checks if the group being currently formed (i.e. next_group)
                contains a message of the given type.
            '''
            return cmd_type in self.state.next_group_commands

        def join_group(cmd: BaseMessage) -> BaseMessage:
            cmd.group = self.state.next_group_id
            self.state.next_group_commands.add(type(cmd))
            return cmd

        def inc_group() -> None:
            self.state.next_group_commands = set()
            self.state.next_group_id += 1

        def inc_group_if(cmd_type: Type[BaseMessage]) -> None:
            if has(cmd_type):
                inc_group()

        if not self.state.next_group_commands:
            # current group is empty -> join it freely
            return join_group(cmd)

        if isinstance(cmd, HaNvecGetEvent):
            # HaNvecGetEvent can be done in parallel to any other commands.
            # No need to form the new group for it.
            return join_group(cmd)

        if isinstance(cmd, AnyEntrypointRequest):
            # if the current group has a BroadcastHAStates request,
            # then this entrypoint request should be placed to a next group.
            inc_group_if(BroadcastHAStates)
            return join_group(cmd)

        if isinstance(cmd, BroadcastHAStates):
            inc_group()
            return join_group(cmd)

        if isinstance(cmd, SnsOperation):
            # Start new group if there is another SNS operation within the
            # current group.
            inc_group_if(SnsOperation)
            return join_group(cmd)

        return join_group(cmd)
