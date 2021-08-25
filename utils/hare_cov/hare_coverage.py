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

from abc import ABC, abstractmethod
from subprocess import Popen, PIPE
from typing import Optional, Callable, List, Dict, Type
from os import walk, sep, path, getcwd
import logging

handlers = [logging.FileHandler('coverage.log'), logging.StreamHandler()]
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=handlers)


class FailedToGenerateReport(BaseException):
    """Used to raise exception while report generation failed."""

    pass


class DirectoryScanner:
    """
    Scans the directory according to the given pattern. It never return files
    which are not listed into 'include' keyword argument.
    """

    def __init__(self,
                 pattern: str,
                 callback: Optional[Callable[[str], bool]] = None,
                 include: str = f"miniprov{sep}test hax{sep}test"):
        """
        Sets a pattern for directory named to be search. Sets the filter for
        other directories not in 'include' keyword argument.
        :param pattern: Directory name to scan
        :param callback: callback for comparison
        :param include: filter out files which are not listed in include kwarg.
        """
        self.pattern = pattern
        self.callback = callback or self.comparator
        self.inc_kwargs = include.split()

    def comparator(self, dir_name: str) -> bool:
        """
        Compares directory name with a set pattern.
        :param dir_name: directory name
        :return: boolean
        """
        return dir_name == self.pattern

    def omit_dir(self, dir_name: str) -> bool:
        """
        Filter out the directories other than listed in include keyword arg.
        :param dir_name: directory name
        :return: boolean
        """
        for word in self.inc_kwargs:
            if dir_name.find(word) > -1:
                return False
        return True

    def search_dir(self, dir_path: str) -> List[str]:
        """
        Strategy for scanning directories.
        :param dir_path: directory path
        :return: List of the file match to given pattern
        """
        result_list: List[str] = []
        for sub_dir, dirs, _ in walk(dir_path):
            for directory in dirs:
                directory_path: str = sub_dir + sep + directory
                if self.omit_dir(directory_path):
                    continue
                result_list.extend([ele for ele in
                                    self.search_dir(directory_path)
                                    if ele not in result_list])
                if self.callback(directory):
                    if directory_path not in result_list:
                        result_list.append(directory_path)
        return result_list


class Utility:
    """Here is the utility class which has static utility helper methods."""

    def run_cmd(self, command: str, delimiter: Optional[str] = None,
                max_split: int = -1) -> str:
        """
        Execute command and return the result.
        :param command: Command in string format
        :param delimiter: delimiter (default is space)
        :param max_split: maximum number split
        :return: tuple(stdout, stderr)
        """
        logging.debug(f"Executing Command : {command!a}")
        process: Popen[bytes] = Popen(
            command.split(sep=delimiter, maxsplit=max_split),
            stdout=PIPE,
            stderr=PIPE)

        out, err = process.communicate()
        if process.returncode:
            raise Exception(
                f'Command {command!a} exited with error code '
                f'{process.returncode}.\n'
                f'Command output: {err.decode("utf-8")}')

        return out.decode('utf-8')

    def is_file_system_node_exist(self, dir_path: str) -> bool:
        """
        Check for the existence of the file system node.
        :param dir_path: file or directory path
        :return: bool
        """
        return path.exists(dir_path)

    def get_abs_hare_home_path(self) -> str:
        """
        Search for the absolute path from where the script can search for
        the test and source directory for unit testcase and coverage run.
        :return: absolute hare home path in string.
        """
        absolute_file_path = path.realpath(__file__)
        pos = absolute_file_path.find(f"utils{sep}hare_cov{sep}"
                                      "hare_coverage.py")
        if pos != -1:
            return absolute_file_path[:pos]
        else:
            logging.error('Not able to get relative hare home path.')
            exit(1)


class Strategy(ABC):
    """Abstract base class for coverage tool."""

    @abstractmethod
    def cleanup(self) -> None:
        """
        Cleaning up old coverage reports.
        :return: None
        """
        pass

    @abstractmethod
    def run_ut(self) -> None:
        """
        Execute unit testcases.
        :return: None
        """
        pass

    @abstractmethod
    def run_coverage(self) -> None:
        """
        Running coverage tool over UTs.
        :return: None
        """
        pass

    @abstractmethod
    def check_report(self) -> None:
        """
        Validate the report generated
        :return: None
        """
        pass


class PythonCoverage(Strategy):

    # This is source to test directory map.It will be used run coverage.
    # All the newly added source and test should be added here for coverage
    # calculation.
    source_test_map_hare: Dict[str, str] = {
        "hax/hax": "hax/test/",
        "provisioning/miniprov/hare_mp": "provisioning/miniprov/test/"
    }

    def __init__(self, cov_report_type: str = "xml",
                 report_dir: str = "hare_coverage_report",
                 st_map: Dict[str, str] = source_test_map_hare.copy()):
        """
        Sets coverage report type, directory where report will generated and
        unit test directories source modules.
        :param cov_report_type: coverage type xml or html
        :param report_dir: directory where report will generated
        :param st_map: source module to test module map
        """
        self.cov_report_type: str = cov_report_type
        self.src_tst_map: Dict[str, str] = st_map
        self.utils = Utility()
        self.abs_path = self.utils.get_abs_hare_home_path()
        self.report_dir = self.abs_path + report_dir
        self.report = self.report_dir + sep
        self.report += (
            "html_report" if self.cov_report_type == "html"
            else "coverage.xml")

        logging.info("Running Python Coverage Tool.")

    def cleanup(self) -> None:
        """
        Cleaning up old coverage reports.
        :return: None
        """
        logging.info("Cleaning up the report.")
        try:
            if self.utils.is_file_system_node_exist(self.report_dir) is True:
                self.utils.run_cmd(f"rm -rf {self.report_dir}")
        except Exception as e:
            logging.error(f"Error {e} while cleanup.")

    def run_ut(self) -> None:
        """
        Execute unit testcases.
        :return: None
        """
        logging.info("Running unit tests.")
        dir_scanner = DirectoryScanner("test")
        for test_dir_path in dir_scanner.search_dir(self.abs_path):
            out: str = self.utils.run_cmd(f"pytest {test_dir_path}")
            logging.info(f"Testcase Results:\n{out}")

    def run_coverage(self) -> None:
        """
        Running coverage tool over UTs.
        :return: None
        """
        logging.info("Running Coverage.")
        command_line: str
        for index, (src, tst) in enumerate(self.src_tst_map.items()):
            if index == 0:
                command_line = f"pytest --cov={self.abs_path}{src} " \
                                    f"--cov-report={self.cov_report_type}:" \
                                    f"{self.report} {self.abs_path}{tst}"
            else:
                command_line = f"pytest --cov={self.abs_path}{src} " \
                                    f"--cov-report={self.cov_report_type}:" \
                                    f"{self.report} --cov-append " \
                                    f"{self.abs_path}{tst}"
            self.utils.run_cmd(command_line)

    def check_report(self) -> None:
        """
        Validate the report generated.
        :return: None
        """
        logging.info("Verify report.")
        if self.utils.is_file_system_node_exist(self.report) is True:
            logging.info("Python Code Coverage Report generated successfully "
                         f"at {self.report!a}.")
        else:
            raise FailedToGenerateReport("Failed to generate the Coverage"
                                         " report. Please check error logs"
                                         f" at '{getcwd()}{sep}coverage.log'")
        out: str = self.utils.run_cmd("coverage report")
        logging.info(f"Python Coverage report:\n{out}")


class CCoverage(Strategy):

    def __init__(self, cov_report_type: str = "xml",
                 report_dir: str = "hare_coverage_report"):
        """
        Sets coverage report type, directory where report will generated.
        :param cov_report_type: coverage type xml or html
        :param report_dir: destination directory where report generated
        """
        self.cov_report_type: str = cov_report_type
        self.utils = Utility()
        self.abs_path = self.utils.get_abs_hare_home_path()
        self.report_dir = self.abs_path + report_dir
        self.report = self.report_dir + sep
        self.report += (
            "html_report" if self.cov_report_type == "html"
            else "c_coverage.xml")

        logging.info("Running C Coverage Tool.")

    def cleanup(self) -> None:
        """
        Cleaning up old coverage reports.
        :return: None
        """
        logging.info("Cleaning up the report.")
        try:
            if self.utils.is_file_system_node_exist(self.report) is True:
                self.utils.run_cmd(f"rm -rf {self.report}")
        except Exception as e:
            logging.error(f"Error {e} while cleanup.")

    def run_ut(self) -> None:
        """
        Execute unit testcases.
        :return: None
        """
        logging.info("Running unit tests.")
        dir_scanner = DirectoryScanner("test")
        for test_dir_path in dir_scanner.search_dir(self.abs_path):
            out: str = self.utils.run_cmd(f"pytest {test_dir_path}")
            logging.info(f"Testcase Results:\n{out}")

    def run_coverage(self) -> None:
        """
        Running coverage tool over UTs.
        :return: None
        """
        logging.info("Running Coverage.")
        command_line: str = f"gcovr -r {self.abs_path}hax{sep} --xml-pretty " \
                            f"-o {self.report}"
        self.utils.run_cmd(command_line)

    def check_report(self) -> None:
        """
        Validate the report generated
        :return: None
        """
        logging.info("Verify report.")
        if self.utils.is_file_system_node_exist(self.report) is True:
            logging.info("Python Code Coverage Report generated successfully "
                         f"at {self.report!a}.")
        else:
            raise FailedToGenerateReport("Failed to generate the Coverage"
                                         " report. Please check error logs"
                                         f" at '{getcwd()}{sep}coverage.log'")
        out: str = self.utils.run_cmd(f"gcovr -r {self.abs_path}hax/")
        logging.info(f"C Coverage report:\n%s", out)


class Executor:

    """
    This class is responsible for the execution of the coverage for both
    python and C.
    """

    def __init__(self, cls: Type[Strategy],
                 report_type: str):
        """
        Sets the strategy class type and related coverage type.
        :param cls: Coverage polymorphic class
        :param report_type: type of the report xml/html
        """
        self._instance = cls(report_type)

    def execute(self) -> None:
        """
        Execute coverage helper functions.
        :return: None
        """
        self._instance.cleanup()
        self._instance.run_ut()
        self._instance.run_coverage()
        self._instance.check_report()


def main() -> None:
    """
    Execute coverage tool for python as well as for c sequentially.
    :return: None
    """
    logging.info(f"Verify the logs at '{getcwd()}{sep}coverage.log'.")
    Executor(PythonCoverage, "xml").execute()
    Executor(CCoverage, "xml").execute()


if __name__ == '__main__':
    main()
