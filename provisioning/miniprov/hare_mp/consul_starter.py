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
import sys
import logging
import logging.handlers
from typing import List
from threading import Event
from hax.types import StoppableThread
from hax.util import ConsulUtil
from hare_mp.utils import (execute_no_communicate, func_log, func_enter,
                           func_leave, LogWriter, Utils)

LOG = logging.getLogger('consul')
LOG_FILE_SIZE = 1024 * 1024 * 1024


class ConsulStarter(StoppableThread):

    """
    Starts consul agent and blocks until terminated.
    """
    def __init__(self, utils: Utils, cns_utils: ConsulUtil, stop_event: Event,
                 log_dir: str, data_dir: str, config_dir: str, node_name: str,
                 node_id: str,
                 peers: List[str],
                 bind_addr: str = '0.0.0.0',  # nosec
                 client_addr: str = '0.0.0.0'):
        super().__init__(target=self._execute,
                         name='consul-starter')
        self.utils = utils
        self.cns_utils = cns_utils
        self.stop_event = stop_event
        self.process = None
        self.log_dir = log_dir
        self.data_dir = data_dir
        self.config_dir = config_dir
        self.node_id = node_id
        self.node_name = node_name
        self.peers = peers
        self.bind_addr = bind_addr
        self.client_addr = client_addr

    @func_log(func_enter, func_leave)
    def stop(self):
        try:
            if self.process:
                self.process.terminate()
        except Exception:
            pass

    @func_log(func_enter, func_leave)
    def _execute(self):
        try:
            log_file = f'{self.log_dir}/hare-consul.log'
            fh = logging.handlers.RotatingFileHandler(log_file,
                                                      maxBytes=LOG_FILE_SIZE,
                                                      mode='a',
                                                      backupCount=5,
                                                      encoding=None,
                                                      delay=False)
            LOG.addHandler(fh)
            console = logging.StreamHandler(stream=sys.stdout)
            LOG.addHandler(console)
            cmd = ['consul', 'agent', f'-bind={self.bind_addr}',
                   f'-advertise={self.bind_addr}',
                   f'-client=127.0.0.1 {self.bind_addr}',
                   '-datacenter=dc1',
                   f'-data-dir={self.data_dir}', '-enable-script-checks',
                   f'-config-dir={self.config_dir}',
                   f'-node={self.node_name}',
                   f'-node-id={self.node_id}',
                   '-domain=consul']
            for peer in self.peers:
                cmd.append(f'-retry-join={peer}')

            restart = True
            while restart:
                try:
                    if self.process:
                        self.process.terminate()
                    self.process = execute_no_communicate(
                        cmd, working_dir=self.log_dir,
                        out_file=LogWriter(LOG, fh))
                    if self.process:
                        self.process.communicate()
                        restart = False
                except Exception:
                    continue
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.info('Stopping Consul')
            self.stop_event.set()
            self.utils.stop_hare()
