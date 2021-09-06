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
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from hax.log import TRACE

__all__ = [
    'supports_consul_cache', 'uses_consul_cache', 'invalidates_consul_cache'
]

LOG = logging.getLogger('hax')


class InvocationCache:
    def __init__(self):
        # function name -> stringified arg list -> returned value
        self._calls: Dict[str, Dict[str, Any]] = {}

    def has(self, fn_name, *args, **kwargs) -> bool:
        if fn_name not in self._calls:
            return False
        v = self._create_key_by_args(*args, **kwargs)
        return v in self._calls[fn_name]

    def get(self, fn_name: str, *args, **kwargs) -> Any:
        param_key = self._create_key_by_args(*args, **kwargs)
        return self._calls[fn_name][param_key]

    def clear(self):
        self._calls = {}

    def put(self, fn_name: str, ret_value: Any, *args, **kwargs):
        fun_dict = self._calls.get(fn_name, {})
        param_key = self._create_key_by_args(*args, **kwargs)
        fun_dict[param_key] = ret_value
        self._calls[fn_name] = fun_dict

    def _create_key_by_args(self, *args, **kwargs) -> str:
        return f'{args}{kwargs}'

    def __repr__(self):
        return 'InvocationCache'


T = TypeVar('T', bound=Callable[..., Any])

kwd_cache = 'kv_cache'


def supports_consul_cache(f: T) -> T:
    """
    Decorates a method that either starts a new cache or silently reuses the
    one provided as kv_cache parameter.
    The function being decorated WILL NOT be cached. The only use case is to
    create the instance of cache that nested functions can pick up.
    """
    @wraps(f)
    def wrapper(*args, **kwds):
        cache: Optional[InvocationCache] = kwds.get(kwd_cache)
        if cache is None:
            LOG.debug('CACHE: created. fn_name=%s', f.__qualname__)
            cache = InvocationCache()

        kwds[kwd_cache] = cache
        ret_value = f(*args, **kwds)
        return ret_value

    return cast(T, wrapper)


def uses_consul_cache(f: T) -> T:
    """
    Decorates a method that needs to be cached when possible.

    General idea of this caching mechanism:

    1. The cache instance is applied as a function argument.
    2. Cache lifecycle is mainly controlled by stack of the calls (when
       the owner frame gets destroyed, cache instance is disposed)
    3. The functions that support caching need to follow some simple
       conventions.
    4. The decorator simplifies the use of the cache and it a kind of
       implements the idea of implicit parameters from Scala programming
       language.
    5. When active, cache accumulates the mapping between the input
       arguments and the result values of the methods decorated by
       @uses_consul_cache decorator.

    Rules how to use this decorator:
    1. Decorated function MUST contain kv_cache keyword argument: kv_cache=None
    2. If the decorated function invokes some other functions decorated with
       this @uses_consul_cache, it MUST propagate its kv_cache argument.
    """
    @wraps(f)
    def wrapper(*args, **kwds):
        # import pudb.remote
        # pudb.remote.set_trace(term_size=(130, 50), port=9998)
        cache: Optional[InvocationCache] = kwds.get(kwd_cache)
        fn_name = f.__qualname__
        if cache is None:
            LOG.debug('CACHE: created. fn_name=%s', fn_name)
            cache = InvocationCache()
            kwds[kwd_cache] = cache

        if cache.has(fn_name, *args, **kwds):
            LOG.log(TRACE, 'CACHE hit: %s', fn_name)
            return cache.get(fn_name, *args, **kwds)
        ret_value = f(*args, **kwds)
        cache.put(fn_name, ret_value, *args, **kwds)
        return ret_value

    return cast(T, wrapper)


def invalidates_consul_cache(f: T) -> T:
    """
    Invalidates the cache instance if it exists.

    See @uses_consul_cache for more details.
    """
    @wraps(f)
    def wrapper(*args, **kwds):
        cache: Optional[InvocationCache] = kwds.get(kwd_cache, None)

        if cache:
            LOG.debug('CACHE: cleared. fn_name=%s', f.__qualname__)
            cache.clear()

        return f(*args, **kwds)

    return cast(T, wrapper)
