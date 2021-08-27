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
import re
from subprocess import PIPE, Popen
from typing import Callable, Dict, List, Optional, Tuple, TypeVar


class Program:
    """
    Holds the command (or chain of commands if pipe `|` is used)
    to be executed by Executor class.
    """
    def __init__(self, cmd: List[str], stdin: Optional['Program'] = None):
        self.cmd = cmd
        self.stdin = stdin

    def __or__(self, other):
        if not isinstance(other, Program):
            return NotImplemented
        other.stdin = self
        return other

    def __repr__(self):
        return f'Program({self.cmd}, stdin={self.stdin})'


class CliException(RuntimeError):
    """
    Main exception class used by the Executor class.
    """
    def __init__(self, stderr: str, code: int, env: Optional[Dict[str, str]],
                 cmd: List[str]):
        """
        stderr - Error output of the CLI command.
        code   - Exit code returned by the command.
        env    - Environment variables used when running the given command.
        cmd    - Failed command.
        """

        super().__init__(stderr)
        self.stderr = stderr
        self.code = code
        self.env = env
        self.cmd = cmd


R = TypeVar('R')
T = TypeVar('T')

OutputConverter = Callable[[str], R]


def as_is(in_value: str) -> str:
    if in_value.endswith('\n'):
        # Cut the final newline
        count = len(in_value)
        return in_value[:count - 1]

    return in_value


def two_columns(in_value: str) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    for line in in_value.splitlines():
        match = re.match(r'^[\s]*([^\s]*)[\s]+([^\s]*)$', line)
        if not match:
            result.append(('', ''))
        else:
            result.append((match.group(1), match.group(2)))
    return result


class Executor:
    """
    CLI Executor. Abstracts from subprocess.Popen and supports single
    commands as well as piped chain of commands.
    """
    def run(self, p: Program, env: Optional[Dict[str, str]] = None) -> str:
        return self.run_ex(p, as_is, env=env)

    def run_ex(self,
               p: Program,
               converter: OutputConverter[T],
               env: Optional[Dict[str, str]] = None) -> T:
        """
        Central method of the executor. Returns either stdout of the executed
        command or raises CliException if the command didn't succeed.
        """

        proc_list: List[Program] = []

        def get_previous(p: Program):
            proc_list.insert(0, p)
            return p.stdin

        p = get_previous(p)
        while p:
            p = get_previous(p)

        prev = None

        for p in proc_list:
            stdin = PIPE
            if prev:
                stdin = prev.stdout

            try:
                logging.debug('Issuing command: %s', p.cmd)
                proc = Popen(p.cmd,
                             stdin=stdin,
                             stdout=PIPE,
                             stderr=PIPE,
                             encoding='utf-8',
                             env=env)
            except FileNotFoundError as e:
                raise CliException(f'Failed to run {p}: {e}',
                                   code=-1,
                                   env=env,
                                   cmd=p.cmd)
            if prev:
                prev.stdout.close()

            prev = proc

        out, err = proc.communicate()
        code = proc.returncode
        if code:
            raise CliException(err, code, env, cmd=p.cmd)
        return converter(out)
