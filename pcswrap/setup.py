import os
from distutils.cmd import Command
from distutils.errors import DistutilsError
from distutils.log import ERROR, INFO
from typing import List, Tuple

from mypy import api
from setuptools import setup, find_packages


class MypyCmd(Command):
    description = 'runs mypy'

    user_options: List[Tuple[str, str, str]] = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        report, errors, exit_code = api.run(['pcswrap'])

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


def get_version():
    v = os.environ.get('PCS_CLIENT_VERSION')
    if v:
        return v
    else:
        return read('../VERSION')


setup(
    cmdclass={'mypy': MypyCmd},
    name='pcswrap',
    version=get_version(),
    packages=find_packages(),
    setup_requires=['flake8', 'mypy', 'pkgconfig'],
    entry_points={'console_scripts': ['pcswrap=pcswrap.client:main']},
)
