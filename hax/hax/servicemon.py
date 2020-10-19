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
"""Service monitoring."""

import logging
from queue import Queue
from threading import Event
from typing import Dict, List

from hax.exception import HAConsistencyException
from hax.message import BroadcastHAStates
from hax.types import HAState, ServiceHealth, StoppableThread
from hax.util import ConsulUtil

LOG = logging.getLogger('hax')


class ServiceMonitor(StoppableThread):

    """
    The service monitoring thread.

    This thread polls the service health status
    from Consul via Health API and broadcasts the states to Motr land.
    """

    def __init__(self, queue: Queue, interval_sec=1):
        """
        Constructor.

        queue - the multithreaded blocking queue to send BroadcastHAStates.
        messages (assuming that the queue is being read out by ConsumerThread).

        interval_sec - float value, represents the delay between the
        polling iterations.
        """
        super().__init__(target=self._execute, name='service-monitor')
        self.stopped = False
        self.consul = ConsulUtil()
        self.interval_sec = interval_sec
        self.event = Event()
        self.q = queue

    def stop(self) -> None:
        """Stop the thread."""
        LOG.debug('Stop signal received')
        self.stopped = True
        self.event.set()

    def _sleep(self, interval_sec) -> bool:
        interrupted = self.event.wait(timeout=interval_sec)
        return interrupted

    def _get_services(self) -> List[str]:
        services = self.consul.catalog_service_names()
        excluded = {'consul'}
        return [s for s in services if s not in excluded]

    def _broadcast(self, state_list: List[HAState]) -> None:
        if not state_list:
            return
        LOG.debug('Changes in statuses: %s', state_list)
        self.q.put(BroadcastHAStates(states=state_list,
                                     is_broadcast_local=False,
                                     reply_to=None))

    def _execute(self):
        service_names: List[str] = self._get_services()
        LOG.debug('The following services will be monitored %s', service_names)
        known_statuses: Dict[str, ServiceHealth] = {
            service: ServiceHealth.UNKNOWN
            for service in service_names
        }
        try:
            while not self.stopped:
                try:
                    delta: List[HAState] = []

                    for name in service_names:
                        health: HAState = self.consul.get_local_service_health(
                                              name)
                        if (health.status != known_statuses[name]):
                            delta.append(health)
                            known_statuses[name] = health.status
                            LOG.debug('%s is now %s', name, health.status)
                    self._broadcast(delta)
                except HAConsistencyException:
                    # No action - we'll just try again at next iteration
                    pass
                self._sleep(self.interval_sec)
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.debug('Thread exited')
