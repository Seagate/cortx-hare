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
import re
from typing import (Any, Dict, Generator, Generic, Iterable, List, Optional,
                    Tuple, Type, TypeVar, cast)

from hax.types import Fid, m0HaObjState
from hax.util import ConsulUtil, TxPutKV, repeat_if_fails

C = TypeVar('C')


class Context:
    """ A type-safe intermittent whiteboard where some parent transitions may
    leave some meta information for nested transitions (e.g. whether the parent
    process is mkfs).
    """
    def __init__(self):
        self.data: Dict[str, Any] = {}

    def put(self, key: str, val: Any) -> 'Context':
        """ Puts the value to the storage and returns the updated instance.
            Note: old instance is not altered by this call.
        """

        # As the context is passed through recursive calls, we don't allow to
        # alter an existing instnace (reason: there is a risk of dirty write
        # somwhere deep in recursion that can affect other transitions in the
        # sequence).
        new_dict = dict(self.data)
        new_dict[key] = val
        ctx = Context()
        ctx.data = new_dict
        return ctx

    def get(self, key: str, as_type: Type[C]) -> C:
        """ Return the value by the key and verify that the value is of the
        given type; if the type doesn't match, RuntimeError is thrown.
        """
        value = self.data.get(key)
        if not isinstance(value, as_type):
            raise RuntimeError(f'Business logic error: {as_type} type '
                               f'expected but {value} is given')

        return value

    def get_or(self, key: str, fallback_value=None) -> Any:
        return self.data.get(key, fallback_value)


class ConsulHelper:
    # This is a kind of a bridge between the ObjectWorfklow and ConsulUtil.
    def __init__(self, cns: Optional[ConsulUtil] = None):
        self.cns = cns or ConsulUtil()

    def get_current_state(self, fid: Fid) -> m0HaObjState:
        """ Reads the latest known state of the object from Consul KV.
        """
        raise RuntimeError('Not implemented')

    def is_proc_client(self, fid: Fid) -> bool:
        raise RuntimeError('Not implemented')

    def get_hax_fid(self) -> Fid:
        raise RuntimeError('Not implemented')

    def get_services_under(self, fid: Fid) -> List[Fid]:
        raise RuntimeError('Not implemented')

    def get_disks_by_service(self, fid: Fid) -> List[Fid]:
        raise RuntimeError('Not implemented')

    def is_mkfs(self, proc_fid: Fid) -> List[Fid]:
        raise RuntimeError('Not implemented')

    def get_kv(self, key: str, ctx: Context) -> str:
        kv_cache = ctx.get_or('kv_cache')
        raw_val = self.cns.kv.kv_get(key, kv_cache=kv_cache)
        return cast(str, raw_val['Value'])

    def is_whole_node_failed(self, proc_fid: Fid, ctx: Context) -> bool:
        kv_cache = ctx.get_or('kv_cache')
        self.cns.get_process_node(proc_fid, kv_cache=kv_cache)
        node = self.cns.get_process_node(proc_fid, kv_cache=kv_cache)
        return self.cns.all_io_services_failed(node, kv_cache=kv_cache)

    def get_process_status_key_pair(self, proc_fid: Fid,
                                    ctx: Context) -> Tuple[str, str]:
        kv_cache = ctx.get_or('kv_cache')
        node_items = self.cns.kv.kv_get('m0conf/nodes',
                                        recurse=True,
                                        kv_cache=kv_cache)
        regex = re.compile(f'^m0conf\\/nodes\\/.*\\/processes\\/{proc_fid}$')
        for item in node_items:
            match_result = re.match(regex, item['Key'])
            if not match_result:
                continue
            return (item['Key'], item['Value'])
        raise KeyError(f'Process {proc_fid} not found in KV')

    @repeat_if_fails()
    def put_kv(self, tx_data: List[TxPutKV]):
        self.cns.kv.kv_put_in_transaction(tx_data)


A = TypeVar('A')


class Pager(Generic[A]):
    """ Splits the given iterable into sequence of lists (pages)
    not greater than page_size.
    """
    def __init__(self, src: Iterable[A], page_size: int):
        self.src = list(src)
        self.size = page_size

    def get_next(self) -> Generator[List[A], None, None]:
        """ Yields the next page. """
        size = self.size
        page = self.src[:size]
        while page:
            yield page
            self.src = self.src[size:]
            page = self.src[:size]
