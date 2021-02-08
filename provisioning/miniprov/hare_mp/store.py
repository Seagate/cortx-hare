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

# Setup utility for Hare to configure Hare related settings, e.g. logrotate,
# report unsupported features, etc.

from typing import Any

from cortx.utils.conf_store import ConfStore


class ValueProvider:
    def get(self, key: str) -> Any:
        return self._raw_get(key)

    def _raw_get(self, key: str) -> str:
        raise NotImplementedError()


class ConfStoreProvider(ValueProvider):
    def __init__(self, url: str):
        self.url = url
        conf = ConfStore()
        conf.load('hare', url)
        self.conf = conf

    def _raw_get(self, key: str) -> str:
        return self.conf.get('hare', key)
