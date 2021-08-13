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

import logging
import threading as thr
from typing import Dict, Optional

from hax.ha.events import Event, EventListener
from hax.ha.handler import EventHandler
from hax.ha.handler.node import NodeEventHandler
from hax.motr.planner import WorkPlanner
from hax.types import StoppableThread
from hax.util import ConsulUtil, InterruptedException, wait_for_event

from ha.core.event_manager.subscribe_event import SubscribeEvent

LOG = logging.getLogger('hax')


class EventPollingThread(StoppableThread):
    """
    Thread which polls the HA events from Kafka by means of EventListener
    class.
    """
    def __init__(self,
                 planner: WorkPlanner,
                 consul: ConsulUtil,
                 listener: Optional[EventListener] = None,
                 interval_sec: float = 1.0):
        """Constructor."""
        super().__init__(target=self._execute,
                         name='ha-event-listener',
                         args=())
        self.stopped = False
        self.event = thr.Event()
        self.interval_sec = interval_sec
        self.receive_timeout = 0.1
        self.cns = consul
        self.raw_listener = listener
        self.planner = planner
        self.handlers: Dict[str, EventHandler] = self._register_handlers()

    def stop(self) -> None:
        LOG.debug('Stop signal received')
        self.stopped = True
        self.event.set()

    def _execute(self):
        LOG.debug('Event polling thread started')
        self.listener = self.raw_listener or self._create_listener()
        try:
            while not self.stopped:
                self._handle_next_messages()
                wait_for_event(self.event, self.interval_sec)
        except InterruptedException:
            # Shutting down normally
            pass
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.debug('HA event listener thread exited')

    def _handle_next_messages(self) -> None:
        timeout = self.receive_timeout

        # Read out and process as many messages we can in a row
        # Once we get no message, the function returns.
        while not self.stopped:
            # TODO one listener listens to one topic only
            # How we're going to listen to a number of topics at the same time?
            # Have multiple listeners?
            msg = self.listener.get_next_message(timeout)
            if not msg:
                break
            self._process(msg)
            self.listener.ack()

    def _register_handlers(self) -> Dict[str, EventHandler]:
        return {'node': NodeEventHandler(self.cns, self.planner)}

    def _process(self, message: Event):
        handlers = self.handlers
        resource_type = message.resource_type
        try:
            LOG.debug('Got message from HA: %s', message)
            if resource_type not in handlers:
                LOG.debug('Message %s is not supported; skipped', message)
                return
            handlers[resource_type].handle(message)

        except Exception as e:
            LOG.warn("Message %s wasn't processed. Reason: %s. Skipped",
                     message, e)
            LOG.debug("Error details:", exc_info=True)

    def _create_listener(self) -> EventListener:
        host = self.cns.get_local_nodename()
        group = f'hare_{host}'
        # group_id stands to Kafka group of consumers
        #
        # Here we make sure that different hax instances use different groups.
        # That means that ack's executed from one hax instance will not affect
        # the messages that another hax instance receives (so every hax reads
        # the whole history of messages even if they process the messages with
        # different speed).
        return EventListener([SubscribeEvent('node', ['offline', 'online'])],
                             group_id=group)
