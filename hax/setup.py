import os
import os.path as P
from distutils.cmd import Command
from distutils.errors import DistutilsError
from distutils.log import ERROR, INFO
from typing import List, Tuple

import pkgconfig
from mypy import api
from setuptools import Extension, setup


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


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)) \
           .read().rstrip('\n')


def get_hax_version():
    v = os.environ.get('HAX_VERSION')
    if v:
        return v
    else:
        return read('../VERSION')


def get_mero_dir():
    try:
        # Mero devel rpm takes precedence over M0_SRC_DIR
        if pkgconfig.exists('mero'):
            return pkgconfig.variables('mero')['includedir']
    except EnvironmentError:
        # fall back to M0_SRC_DIR handling if `pkg-config` is not available in
        # the system
        pass

    d = os.environ.get('M0_SRC_DIR')
    if d:
        return d
    return P.normpath(P.dirname(P.abspath(__file__)) + '/../../mero')


def get_mero_libs_dir():
    try:
        # Mero devel rpm takes precedence over M0_SRC_DIR
        if pkgconfig.exists('mero'):
            return pkgconfig.variables('mero')['libdir']
    except EnvironmentError:
        # fall back to M0_SRC_DIR handling if `pkg-config` is not available in
        # the system
        pass

    libs_dir = get_mero_dir() + '/mero/.libs'
    libmero = libs_dir + '/libmero.so'
    assert P.isfile(libmero), f'{libmero}: No such file'
    return libs_dir


def get_mero_cflags():
    try:
        # Mero devel rpm takes precedence over M0_SRC_DIR
        if pkgconfig.exists('mero'):
            return pkgconfig.cflags('mero').split()
    except EnvironmentError:
        # fall back to M0_SRC_DIR handling if `pkg-config` is not available in
        # the system
        pass

    return [
        '-g', '-Werror', '-Wall', '-Wextra', '-Wno-attributes',
        '-Wno-unused-parameter'
    ]


setup(
    cmdclass={'mypy': MypyCmd},
    name='hax',
    version=get_hax_version(),
    packages=['hax'],
    setup_requires=['flake8', 'mypy', 'pkgconfig'],
    install_requires=['python-consul>=1.1.0'],
    entry_points={'console_scripts': ['hax=hax.hax:main']},
    ext_modules=[
        Extension(
            name='libhax',
            sources=['hax/hax.c'],
            include_dirs=[get_mero_dir(),
                          get_mero_dir() + '/extra-libs/galois/include'],
            define_macros=[('M0_INTERNAL', ''), ('M0_EXTERN', 'extern')],
            library_dirs=[get_mero_libs_dir()],
            runtime_library_dirs=[get_mero_libs_dir()],
            libraries=['mero'],
            extra_compile_args=[x for x in get_mero_cflags() + ['-fPIC']])
    ],
)
