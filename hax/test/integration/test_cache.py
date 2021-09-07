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

import pytest
from hax.consul.cache import uses_consul_cache

from .testutils import AssertionPlan, tr_method, trace_call


class Testable:
    @trace_call
    def heavy_method(self, arg):
        return arg


@pytest.fixture
def testable() -> Testable:
    return Testable()


def test_same_signatures_cached(testable):
    @uses_consul_cache
    def business_op(param1, kv_cache=None):
        return testable.heavy_method(param1)

    @uses_consul_cache
    def cache_holder(kv_cache=None):
        return [business_op("result", kv_cache=kv_cache) for i in range(5)]

    results = cache_holder()
    assert ['result'] * 5 == results, \
        'Cache spoils returned values'

    assert AssertionPlan(tr_method('heavy_method')).count(testable.traces) == 1


def test_arguments_considered_by_cache(testable):
    @uses_consul_cache
    def business_op(param1, kv_cache=None):
        return testable.heavy_method(param1)

    @uses_consul_cache
    def cache_holder(kv_cache=None):
        return [business_op(i & 1, kv_cache=kv_cache) for i in range(5)]

    results = cache_holder()
    assert [0, 1, 0, 1, 0] == results, \
        'Cache spoils returned values'

    assert AssertionPlan(tr_method('heavy_method')).count(testable.traces) == 2
