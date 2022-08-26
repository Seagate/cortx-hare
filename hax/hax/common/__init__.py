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
"""Hax commons package symbols."""
import inject


class HaxGlobalState:

    """Global state of whole Hax application."""
    def __init__(self):
        """Initialize current state to non-stopping state."""
        self.stopping: bool = False

    def is_stopping(self) -> bool:
        """Whether the application is stopping now."""
        return self.stopping

    def set_stopping(self):
        """Switches the current state to 'stopping' state."""
        self.stopping = True


def di_configuration(binder: inject.Binder):
    """Configures Dependency Injection (DI) engine."""
    binder.bind(HaxGlobalState, HaxGlobalState())
