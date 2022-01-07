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
"""Module for cortx-ha integration."""

import logging

from hax.motr.planner import WorkPlanner
from hax.types import StoppableThread
from hax.util import ConsulUtil
from cortx.utils.message_bus import MessageBus
from cortx.utils.conf_store import Conf

__all__ = ['create_ha_thread']

LOG = logging.getLogger('hax')


class StubEventThread(StoppableThread):
    """Stub implementation of EventPollingThread.

    The class is used as a Null Object pattern in cases when
    cortx-ha types can't be imported. The only aim of this thread
    is to log the corresponding message and exit gracefully.
    """
    def __init__(self):
        super().__init__(target=self._execute, name='ha-event-listener')

    def _execute(self):
        LOG.info('cortx-ha component is not present. HaX will '
                 'contunie working without HA integration')


def create_ha_thread(planner: WorkPlanner,
                     util: ConsulUtil) -> StoppableThread:
    """Creates the proper HA-aware thread, handling possible import errors."""
    try:
        from .thread import EventPollingThread
        _ha_message_bus_init(util)
        return EventPollingThread(planner, util)
    except ImportError:
        return StubEventThread()


def _ha_message_bus_init(util: ConsulUtil):
    """
    This creates a MessageBus internal global in-memory object which is
    indirectly part of the process address space. Thus
    `MessageBus.init()` must be invoked within process's address space.
    """
    configpath = util.get_configpath()
    Conf.load('cortx_conf', configpath)

    message_server_endpoints = Conf.get('cortx_conf',
                                        'cortx>external>kafka>endpoints')
    MessageBus.init(message_server_endpoints)
