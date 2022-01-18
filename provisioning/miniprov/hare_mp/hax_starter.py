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
import sys
from threading import Event
import os
from hax.types import StoppableThread
from hare_mp.utils import (execute_no_communicate, func_log, func_enter,
                           func_leave, LogWriter, Utils)

LOG = logging.getLogger('hax')
LOG_FILE_SIZE = 1024 * 1024 * 1024


class HaxStarter(StoppableThread):
    """
    Starts consul agent and blocks until terminated.
    """
    def __init__(self, utils: Utils, stop_event: Event, home_dir: str,
                 log_dir: str):
        super().__init__(target=self._execute,
                         name='hax-starter')
        self.utils = utils
        self.stop_event = stop_event
        self.process = None
        self.home_dir = home_dir
        self.log_dir = log_dir

    @func_log(func_enter, func_leave)
    def stop(self):
        try:
            if self.process:
                self.process.kill()
        except Exception:
            pass

    @func_log(func_enter, func_leave)
    def _execute(self):
        try:
            hax_log_file = f'{self.log_dir}/hare-hax.log'
            fh = logging.handlers.RotatingFileHandler(hax_log_file,
                                                      maxBytes=LOG_FILE_SIZE,
                                                      mode='a',
                                                      backupCount=5,
                                                      encoding=None,
                                                      delay=False)
            LOG.addHandler(fh)
            path = os.getenv('PATH', '')
            path += os.pathsep + '/opt/seagate/cortx/hare/bin'
            path += os.pathsep + '/opt/seagate/cortx/hare/libexec'
            python_path = os.pathsep.join(sys.path)
            cmd = ['hax']
            restart = True
            while restart:
                try:
                    if self.process:
                        self.process.terminate()
                    self.process = execute_no_communicate(
                        cmd, env={'PYTHONPATH':
                                  python_path,
                                  'PATH': path,
                                  'LC_ALL': "en_US.utf-8",
                                  'LANG': "en_US.utf-8"},
                        working_dir=self.home_dir,
                        out_file=LogWriter(LOG, fh))
                    if self.process:
                        self.process.communicate()
                        restart = False
                except Exception:
                    continue
        except Exception:
            LOG.exception('Aborting due to an error')
        finally:
            LOG.debug('Stopping Hax')
            self.stop_event.set()
            self.utils.stop_hare()
