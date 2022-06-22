# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License
# for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
# For any questions about this software or licensing, please email
# opensource@seagate.com or cortx-questions@seagate.com.

import json
from typing import Dict, List, Optional
from hax.configmanager import ConfigManager

cached_subscriber_list: List = []
is_subscriber_list_cached: bool = False


class HaUtils:
    resource_types = ['node']
    interface_types = ['health_message']

    def __init__(self, consul_util: ConfigManager):
        self.util = consul_util
        self.get_subscribers(self.util, None)

    # If resourse_type is None then all resource_types will be fetched
    def get_subscribers(self, consul_util: ConfigManager,
                        resourse_type: Optional[str]):
        global cached_subscriber_list, is_subscriber_list_cached
        subscriber_list: List = []
        if is_subscriber_list_cached:
            return cached_subscriber_list

        if resourse_type:
            subscribers = consul_util.kv.kv_get(
                                f'events/subscription/{resourse_type}',
                                allow_null=True)
            subscriber_list = json.loads(subscribers['Value'])
        else:
            for resourse_type in self.resource_types:
                subscribers = consul_util.kv.kv_get(
                                    f'events/subscription/{resourse_type}',
                                    allow_null=True)
                if subscribers:
                    subscriber_list.append(json.loads(subscribers['Value']))
        cached_subscriber_list = subscriber_list
        is_subscriber_list_cached = True
        return subscriber_list

    def event_subscribe(self, data: Dict[str, str]):
        global cached_subscriber_list
        for item in data.keys():
            if item not in self.resource_types:
                raise Exception(f'Invalid resource type({item})')
            if data[item] not in self.interface_types:
                raise Exception(f'Invalid interface type({data[item]})')

            subscriber = self.util.kv.kv_get(f'events/subscription/{item}',
                                             allow_null=True)
            subscriber_list = []
            if subscriber:
                subscriber_list = json.loads(subscriber['Value'])
            if data[item] not in subscriber_list:
                subscriber_list.append(data[item])
            self.util.kv.kv_put(f'events/subscription/{item}',
                                json.dumps(subscriber_list))
            cached_subscriber_list = subscriber_list

    def event_unsubscribe(self, data: Dict[str, str]):
        global cached_subscriber_list
        for item in data.keys():
            if item not in self.resource_types:
                raise Exception(f'Invalid reource type({item})')
            if data[item] not in self.interface_types:
                raise Exception(f'Invalid interface type({data[item]})')

            subscriber = self.util.kv.kv_get(f'events/subscription/{item}',
                                             allow_null=True)
            subscriber_list = []
            if subscriber:
                subscriber_list = json.loads(subscriber['Value'])
            if data[item] in subscriber_list:
                subscriber_list.remove(data[item])
            self.util.kv.kv_put(f'events/subscription/{item}',
                                json.dumps(subscriber_list))
            cached_subscriber_list = subscriber_list
