import re
from subprocess import PIPE, Popen
from typing import Any, List

import defusedxml.ElementTree as ET

from pcswrap.exception import CliException, PcsNoStatusException
from pcswrap.types import Node, PcsConnector


class CliExecutor:
    def get_full_status_xml(self) -> str:
        return self._execute(['pcs', 'status', '--full', 'xml'])

    def get_status_text(self) -> str:
        return self._execute(['pcs', 'status'])

    def standby_node(self, node_name: str) -> None:
        self._execute(['pcs', 'node', 'standby', node_name])

    def unstandby_node(self, node_name: str) -> None:
        self._execute(['pcs', 'node', 'unstandby', node_name])

    def unstandby_all(self) -> None:
        self._execute(['pcs', 'node', 'unstandby', '--all'])

    def standby_all(self) -> None:
        self._execute(['pcs', 'node', 'standby', '--all'])

    def shutdown_node(self, node_name: str) -> None:
        self._execute(['pcs', 'stonith', 'fence', node_name, '--off'])

    def _execute(self, cmd: List[str]) -> str:
        process = Popen(cmd,
                        stdin=PIPE,
                        stdout=PIPE,
                        stderr=PIPE,
                        encoding='utf8')

        out, err = process.communicate()
        exit_code = process.returncode
        if exit_code:
            raise CliException(out, err, exit_code)
        return out


class CliConnector(PcsConnector):
    def __init__(self, executor: CliExecutor = None):
        self.executor: CliExecutor = executor or CliExecutor()

    def get_nodes(self) -> List[Node]:
        def to_node(tag) -> Node:
            return Node(name=tag.attrib['name'],
                        online='true' == tag.attrib['online'],
                        shutdown='true' == tag.attrib['shutdown'],
                        standby='true' == tag.attrib['standby'])

        xml_str = self.executor.get_full_status_xml()
        xml = self._parse_xml(xml_str)

        result: List[Node] = [
            to_node(tag) for tag in xml.findall('./nodes/node')
        ]
        return result

    def get_cluster_name(self) -> str:
        out = self.executor.get_status_text()
        regex = r'^Cluster name:[\s]+(.*)$'
        for line in out.splitlines():
            m = re.match(regex, line)
            if m:
                return m.group(1)
        raise PcsNoStatusException('Failed to find cluster name: pcs status'
                                   ' command output was not recognized')

    def _parse_xml(self, xml_str: str) -> Any:
        try:
            xml = ET.fromstring(xml_str)
            return xml
        except ET.ParseError:
            raise PcsNoStatusException('Broken XML was given')

    def standby_node(self, node_name: str) -> None:
        self.executor.standby_node(node_name)

    def unstandby_node(self, node_name: str) -> None:
        self.executor.unstandby_node(node_name)

    def standby_all(self) -> None:
        self.executor.standby_all()

    def unstandby_all(self) -> None:
        self.executor.unstandby_all()

    def shutdown_node(self, node_name: str) -> None:
        self.executor.shutdown_node(node_name)
