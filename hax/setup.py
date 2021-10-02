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

import os
import os.path as P
import re
from distutils.cmd import Command
from distutils.errors import DistutilsError
from distutils.log import ERROR, INFO
from typing import Dict, List, Tuple

import pkgconfig
from mypy import api
from setuptools import Extension, find_packages, setup


class MypyCmd(Command):
    description = 'runs mypy'

    user_options: List[Tuple[str, str, str]] = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        report, errors, exit_code = api.run(['hax'])

        if report:
            self.announce(report, level=INFO)
        if errors:
            self.announce(errors, level=ERROR)
        if exit_code:
            # According to the source code, such exception is the only way to
            # mark this build step as failed.
            raise DistutilsError(
                f'Mypy returned {exit_code}. Exiting with FAILURE status')


def get_abs_path(fname: str):
    return os.path.join(os.path.dirname(__file__), fname)


def read(fname):
    return open(get_abs_path(fname)) \
        .read().rstrip('\n')


def read_lines(fname):
    with open(get_abs_path(fname)) as f:
        return f.readlines()


def get_hax_version():
    v = os.environ.get('HAX_VERSION')
    if v:
        return v
    else:
        return read('../VERSION')


def get_motr_dir():
    try:
        # Motr devel rpm takes precedence over M0_SRC_DIR
        if pkgconfig.exists('motr'):
            return pkgconfig.variables('motr')['includedir']
    except EnvironmentError:
        # fall back to M0_SRC_DIR handling if `pkg-config` is not available in
        # the system
        pass

    d = os.environ.get('M0_SRC_DIR')
    if d:
        return d
    return P.normpath(P.dirname(P.abspath(__file__)) + '/../../cortx-motr')


def get_motr_libs_dir():
    try:
        # Motr devel rpm takes precedence over M0_SRC_DIR
        if pkgconfig.exists('motr'):
            return pkgconfig.variables('motr')['libdir']
    except EnvironmentError:
        # fall back to M0_SRC_DIR handling if `pkg-config` is not available in
        # the system
        pass

    libs_dir = get_motr_dir() + '/motr/.libs'
    libmotr = libs_dir + '/libmotr.so'
    assert P.isfile(libmotr), f'{libmotr}: No such file'
    return libs_dir


def get_galois_include_dir():
    motr_dir = get_motr_dir()
    return f'{motr_dir}/extra-libs/galois/include/'


def get_motr_cflags():
    try:
        # Motr devel rpm takes precedence over M0_SRC_DIR
        if pkgconfig.exists('motr'):
            return pkgconfig.cflags('motr').split()
    except EnvironmentError:
        # fall back to M0_SRC_DIR handling if `pkg-config` is not available in
        # the system
        pass

    return [
        '-g', '-Werror', '-Wall', '-Wextra', '-Wno-attributes',
        '-Wno-unused-parameter', '-include', 'config.h'
    ]


def get_requirements():
    result: Dict[str, List[str]] = {'build': [], 'runtime': []}
    key = 'build'

    def is_comment(line: str) -> bool:
        return re.match(r'^\s*#', line) is not None

    def is_empty(line: str) -> bool:
        return line.strip() == ''

    def is_runtime_comment(line: str) -> bool:
        return re.match(r'^\s*#:runtime-requirements:', line) is not None

    for line in read_lines('requirements.txt'):
        if is_runtime_comment(line):
            key = 'runtime'
            continue
        if is_comment(line) or is_empty(line):
            continue
        result[key].append(line.strip())

    return result


reqs = get_requirements()

setup(
    cmdclass={'mypy': MypyCmd},
    name='hax',
    version=get_hax_version(),
    packages=find_packages(),
    setup_requires=reqs['build'],
    install_requires=reqs['runtime'],
    entry_points={
        'console_scripts': [
            'hax=hax.hax:main', 'q=hax.queue.cli:main',
            'configure=helper.configure:main',
            'update-conf=helper.update_conf:main'
        ]
    },
    ext_modules=[
        Extension(
            name='libhax',
            sources=['hax/motr/hax.c'],
            include_dirs=[get_motr_dir(),
                          get_galois_include_dir()],
            define_macros=[('M0_INTERNAL', ''), ('M0_EXTERN', 'extern')],
            library_dirs=[get_motr_libs_dir()],
            runtime_library_dirs=[get_motr_libs_dir()],
            libraries=['motr'],
            extra_compile_args=[x for x in get_motr_cflags() + ['-fPIC']])
    ],
)
