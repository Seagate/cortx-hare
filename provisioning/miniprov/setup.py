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

import pkgconfig
from setuptools import find_packages, setup

setup(name='hare_mp',
      version='0.0.1',
      packages=find_packages(),
      setup_requires=['flake8', 'mypy', 'pkgconfig'],
      install_requires=['setuptools', 'dataclasses'],
      package_data={'': '*.dhall'},
      entry_points={'console_scripts': ['setup_hare=hare_mp.main:main']})
