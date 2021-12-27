# Copyright (c) 2021 Seagate Technology LLC and/or its Affiliates
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

import base64
import json
import logging
import re
from threading import Condition
from typing import Dict, List, Optional, Tuple

from hax.exception import InterruptedException
from hax.types import StoppableThread
from hax.util import KVAdapter, repeat_if_fails

from .rule import (EqMessageHandler, NullHandler, ProcHealthUpdateHandler,
                   StobIoqErrorHandler)
from .message import STOB_IOQ, PROCESS_HEALTH

LOG = logging.getLogger('hax')


class Synchronizer:
    """ Thread synchronizing primitive for RCProcessorThread. There are two
    main aims:

    1. Make sure that RCProcessorThread is idle if and only if the
       current node is not an RC leader.
    2. Help RCProcessorThread to exit
       gracefully when the application is shutting down.
    """
    def __init__(self):
        self.lock = Condition()
        self.stopping: bool = False
        self.wait_timeout: float = 2.0
        self.pause_needed: bool = True
        self.leader: bool = False

    def ensure_allowed(self):
        """ The method blocks until the current thread is allowed to run (i.e.
        RC leadership is acquired). Raises InterruptedException if the
        application is shutting down (so that the caller should use this
        exception for graceful shutdown).
        """
        with self.lock:
            while True:
                if self.stopping:
                    raise InterruptedException('Application is shutting down')
                if self.leader:
                    LOG.debug('I am RC leader')
                    if self.pause_needed:
                        self.pause_needed = False
                        # TODO revisit this logic
                        # This implementation assumes that any time the new RC
                        # leader starts working, it must wait for 2 seconds
                        # first.
                        # This approach causes delays but they are not always
                        # required (e.g. it may happen that there are NO former
                        # RC leaders that are finishing their job. If we think
                        # of the way how to learn that, then we can avoid extra
                        # pauses.
                        LOG.debug(
                            "I'll sleep for %s seconds to allow former "
                            'RC leader to finish the work', self.wait_timeout)
                        self.lock.wait(self.wait_timeout)
                        LOG.debug("Fine, let me check if I'm still a leader")
                        continue
                    return
                self.lock.wait()

    def set_leader(self, is_leader: bool):
        """ Marks current hax as RC leader (or revokes the leadership if
        `is_leader` is False).

        If the method is invoked with True parameter then the RCProcessorThread
        will start processing EQ message queue as the RC leader.  If the method
        is invoked with False, RCProcessorThread may still be finishing
        processing of an EQ message (so it will not be canceled right away. The
        thread will just not take a new EQ message if the leadership is lost.
        """
        with self.lock:
            was = self.leader
            self.leader = is_leader
            if is_leader:
                self.pause_needed = not was
                if not was:
                    LOG.debug('Unblocking RC leader thread: the leadership '
                              'is now acquired!')
            else:
                if was:
                    LOG.debug('Current node is not an RC leader anymore. RC '
                              'leader thread will be blocked')
                self.pause_needed = True
            self.lock.notify()

    def sleep(self, timeout: float):
        """ Blocks the current thread for `timeout` number of seconds. The
        thread may be awakened earlier if either `set_leader()` is invoked or
        the application is shutting down.
        """
        with self.lock:
            self.lock.wait(timeout)


class MessageProvider:
    """
    Encapsulates some KV-related logic so that RCProcessorThread doesn't
    interact with Consul KV directly (as a result, its functionality is easier
    to cover with tests).
    """
    def __init__(self, kv: KVAdapter):
        self.kv = kv

    @repeat_if_fails(wait_seconds=0.25)
    def get_next_message(self) -> Optional[Tuple[int, Dict[str, str]]]:
        """ Returns the next unprocessed EQ message.
        """
        # Note that we intentionally leave trailing slash at the end.
        # If we request 'eq' with recurse flag, by some reason 'eq-epoch' key
        # may be returned.
        messages: List[Dict[str, str]] = self.kv.kv_get('eq/', recurse=True)

        def get_key(item: Dict[str, str]) -> int:
            key = item['Key']
            match = re.match(r'^.*\/(\d+)$', key)
            if not match:
                raise RuntimeError('Unexpected key is met: %s', key)
            return int(match.group(1))

        if not messages:
            return None
        min_item = (get_key(messages[0]), messages[0])
        for m in messages:
            k = get_key(m)
            if k < min_item[0]:
                min_item = (k, m)

        return min_item

    @repeat_if_fails(wait_seconds=0.25)
    def remove_message(self, consul_key: str):
        self.kv.kv_del(consul_key)


class RCProcessorThread(StoppableThread):
    """
    Thread that executes the logic of RC leader in HaX. Each HaX instance has
    this thread but only one of them will be active.
    """
    def __init__(self, synchronizer: Synchronizer, kv_adapter: KVAdapter):
        """Constructor."""
        super().__init__(target=self._execute, name='rc-processor', args=())
        self.synchronizer = synchronizer
        self.provider = MessageProvider(kv_adapter)

    def stop(self):
        """Stops the thread gracefully."""
        synch = self.synchronizer
        with synch.lock:
            synch.stopping = True
            synch.lock.notify()

    def _execute(self):
        LOG.debug('RC processing thread started')
        synch = self.synchronizer
        try:
            while True:
                synch.ensure_allowed()
                self._process_next()

        except InterruptedException:
            LOG.debug('Shutting down gracefully')
        except Exception:
            LOG.exception('Unexpected error')
        finally:
            LOG.debug('RC processing thread exited')

    def _process_next(self):
        raw_msg = self.provider.get_next_message()
        if not raw_msg:
            self.synchronizer.sleep(0.5)
            return
        key, msg = raw_msg
        self._process_message(msg)
        LOG.debug('Message [offset=%s] is processed. Removing it from EQ.',
                  key)
        self.provider.remove_message(msg['Key'])

    def _process_message(self, msg: Dict[str, str]):
        LOG.debug('Started processing message %s', msg)
        try:
            b_value: bytes = base64.b64decode(msg['Value'])
            str_val = b_value.decode('utf-8')
            parsed_obj = json.loads(str_val)
            msg_type = parsed_obj['message_type']
            handler = self._get_msg_handler(msg_type)
            handler.handle(msg_type, parsed_obj['payload'])
        except Exception as e:
            LOG.warn(
                'Failed to process EQ message [offset=%s]: %s. '
                'Skipped.', msg['Key'], e)

    def _get_msg_handler(self, msg_type: str) -> EqMessageHandler:
        if msg_type == STOB_IOQ:
            return StobIoqErrorHandler()
        elif msg_type == PROCESS_HEALTH:
            return ProcHealthUpdateHandler()
        else:
            return NullHandler()
