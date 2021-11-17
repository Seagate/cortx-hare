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

import time
from dataclasses import dataclass
from typing import Any, Callable, List, Tuple

from hax.motr.ffi import HaxFFI
from hax.types import MessageId


@dataclass
class Invocation:
    method_name: str
    args: List[Any]
    called_ts: float


def trace_call(fn):
    '''
    Decorator that 'logs' the historical sequence of all the methods of the
    given class.

    The implementation assumes that
    1. the decorator will decorate methods of a class (not static functions).
    2. the class has field `traces: List[Invocation]`
    '''
    def wrapper(self, *args, **kwargs):
        ts = time.time()
        args_copy = [i for i in args]
        name = fn.__name__
        if not hasattr(self, 'traces'):
            self.traces = []
        self.traces.append(Invocation(name, args_copy, ts))
        return fn(self, *args, **kwargs)

    return wrapper


@dataclass
class AssertionState:
    traces: List[Invocation]
    result: bool
    found_at: int


TraceMatcher = Callable[[Invocation], bool]
TracePredicate = Callable[[List[Invocation]], int]
StateTransformer = Callable[[AssertionState], AssertionState]


class AssertionPlan:
    '''
    Convenient mini-API for checking the traces left by `@trace_call`.

    Example of usage:

    assert AssertionPlan(
        tr_method('ha_broadcast')).run(traces), 'ha_broadcast must be invoked'

    assert AssertionPlan(
        tr_method('ha_broadcast')).and_then(
            tr_method('entrypoint_reply')).run(traces),
            'ha_broadcast must be invoked before entrypoint_reply'
    '''
    def __init__(self, first: TraceMatcher):
        self.steps: List[Tuple[StateTransformer,
                               TracePredicate]] = [(self._id(),
                                                    self._exec(first))]

    def and_then(self, predicate: TraceMatcher) -> 'AssertionPlan':
        '''
        Orders the predicates in the historical order (what call happened after
        which call). In other words, this method helps to build the predicates
        like this:

            1. Check that method X was invoked (specified by some matcher)
            2. And check that method Y was invoked afterwards (also specified
               by some matcher)

        '''
        self.steps.append((self._after(), self._exec(predicate)))
        return self

    def exists(self, traces: List[Invocation]) -> bool:
        '''
        Evaluates the steps in this AssertionPlan and returns the final result
        of the assertion.
        '''
        state = AssertionState(traces, False, -1)
        for transformer, predicate in self.steps:
            state = transformer(state)
            if state.result:
                return True
            res = predicate(state.traces)
            if res >= 0:
                state = AssertionState(state.traces, True, res)
        return state.result

    def count(self, traces: List[Invocation]) -> int:
        """
        Counts how many traces in the list correspond to the given criteria.
        """
        def _eval(state: AssertionState, steps: List[Tuple[StateTransformer,
                                                           TracePredicate]],
                  count: int) -> int:
            if not steps:
                return count

            transformer, predicate = steps[0]
            xs = steps[1:]

            while True:
                state = transformer(state)
                res = predicate(state.traces)
                if res < 0:
                    break

                state = AssertionState(state.traces[res + 1:], True, -1)
                count = max(_eval(state, xs, count + 1), count)
            return count

        state = AssertionState(traces, False, -1)
        return _eval(state, self.steps, 0)

    def not_exists(self, traces: List[Invocation]) -> bool:
        '''
        Evaluates the steps in this AssertionPlan and returns True if
        match is not found.
        '''
        state = AssertionState(traces, False, -1)
        for transformer, predicate in self.steps:
            state = transformer(state)
            res = predicate(state.traces)
            if res >= 0:
                return False
        return True

    def _id(self):
        def fn(state: AssertionState) -> AssertionState:
            return state

        return fn

    def _after(self):
        def fn(state: AssertionState) -> AssertionState:
            last_idx = state.found_at
            return AssertionState(traces=state.traces[:last_idx + 1],
                                  result=state.result,
                                  found_at=-1)

        return fn

    def _exec(self, matcher: TraceMatcher) -> TracePredicate:
        def fn(traces: List[Invocation]) -> int:
            i = 0
            for call in traces:
                if matcher(call):
                    return i
                i += 1
            return -1

        return fn


def tr_method(name: str) -> TraceMatcher:
    '''
    Matcher for AssertionPlan that matches the invocation by the method name.
    '''
    def fn(trace: Invocation) -> bool:
        return trace.method_name == name

    return fn


def tr_not(matcher: TraceMatcher) -> TraceMatcher:
    '''
    Inverts the result of the nested matcher.
    '''
    def fn(trace: Invocation) -> bool:
        return not matcher(trace)

    return fn


def tr_and(*matchers: TraceMatcher) -> TraceMatcher:
    '''
    Matcher for AssertionPlan that works as logical AND for the matchers
    passed via arguments.
    '''
    def fn(trace: Invocation) -> bool:
        res = True
        for m in matchers:
            res = res and m(trace)
            if not res:
                break
        return res

    return fn


class FakeFFI(HaxFFI):
    def __init__(self):
        self.traces: List[Invocation] = []

    @trace_call
    def init_motr_api(self, ptr, some_str):
        return 1

    @trace_call
    def start(self, ctx, endpoint, process_fid, ha_fid, rm_fid):
        ...

    @trace_call
    def start_rconfc(self):
        ...

    @trace_call
    def motr_stop(self, ha_ctx):
        ...

    @trace_call
    def stop_rconfc(self, ha_ctx):
        ...

    @trace_call
    def ha_broadcast(self, _ha_ctx, ha_notes, notes_len):
        return [MessageId(101, 1), MessageId(101, 2)]

    @trace_call
    def entrypoint_reply(self, *args):
        return 1

    @trace_call
    def hax_stop(self, *args):
        return [MessageId(111, 1)]

    @trace_call
    def ha_nvec_reply(self, _ha_ctx, ha_notes, notes_len):
        return [MessageId(101, 1), MessageId(101, 2)]
