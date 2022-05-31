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
#
import unittest
from typing import List

from hare_mp.systemd import HaxUnitTransformer


class TestHaxUnitTrasform(unittest.TestCase):
    def test_empty_source_results_empty(self):
        source: List[str] = []
        output = HaxUnitTransformer().transform(source)
        self.assertEqual([], output)

    def test_restart_commented(self):
        source: List[str] = ['Restart=on-failure']
        output = HaxUnitTransformer().transform(source)
        self.assertRegex(output[0], r'^#.*')

    def test_not_everything_commented(self):
        source = '''[Unit]
Description=HAX daemon for Hare
Requires=hare-consul-agent.service motr-kernel.service
After=hare-consul-agent.service motr-kernel.service

[Service]
# TODO: '/opt/seagate/cortx/hare' prefix can be different, e.g. '/usr'
SyslogIdentifier=hare-hax
Environment=PYTHONPATH=/opt/seagate/cortx/hare/lib64/python3.6/site-packages:/opt/seagate/cortx/hare/lib/python3.6/site-packages
ExecStart=/bin/sh -c 'cd $HOME/seagate/var/motr/hax && exec /opt/seagate/cortx/hare/bin/hax'
KillMode=process'''
        output = HaxUnitTransformer().transform(source.splitlines())
        self.assertEqual(source, '\n'.join(output))
