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
from dataclasses import dataclass
from typing import Generic, Iterable, Optional, TypeVar

A = TypeVar('A')


@dataclass
class Elem(Generic[A]):
    data: A
    next_elem: 'Optional[Elem[A]]' = None


class LinkedListIterator:
    def __init__(self, q):
        self.cur = q.head

    def __iter__(self):
        return self

    def __next__(self):
        if not self.cur:
            raise StopIteration()
        ret = self.cur
        self.cur = ret.next_elem
        return ret.data


class LinkedList(Iterable[A]):

    ''' The class is used as a replacement for set() in cases when the stored
    objects are not hashable and it is sufficient to compare them by 'identity'
    (the equality of memory pointer).
    '''
    head: Optional[Elem[A]]

    def __init__(self):
        self.head = None

    def add(self, value: A) -> None:
        elem = Elem(data=value)
        old_head = self.head
        self.head = elem
        elem.next_elem = old_head

    def remove(self, value: A) -> bool:
        prev: Optional[Elem[A]] = None
        q = self.head
        while q:
            if q.data is value:
                if not prev:
                    self.head = q.next_elem
                else:
                    prev.next_elem = q.next_elem
                return True
            prev = q
            q = q.next_elem
        return False

    def __contains__(self, value: A) -> bool:
        # This supports 'in' operator
        q = self.head
        while q:
            if q.data is value:
                return True
            q = q.next_elem
        return False

    def __bool__(self) -> bool:
        # This adds support of 'not' operator in terms of emptyness.
        # 'if not linked_set' evaluates to True <=> the set is empty
        return bool(self.head)

    def __iter__(self):
        return LinkedListIterator(self)

    def __repr__(self):
        if not self.head:
            return '<empty>'
        return '(' + ', '.join(str(s) for s in self) + ')'
