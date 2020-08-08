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

from typing import Any, Tuple, Dict, List

# This is a stub file for `defusedxml` module so that mypy will be able
# to validate the code leveraging the library.
#
# NOTE: The stub is not complete so whenever pcsclient starts using more functions
# from the library, the developers are encouraged to improve and extend this stub.

def fromstring(v: str) -> Any: ...

class ParseError(SyntaxError): ...
