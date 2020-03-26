import logging
import re
from subprocess import PIPE, Popen
from typing import Any, List

import defusedxml.ElementTree as ET

from pcswrap.exception import CliException, PcsNoStatusException
from pcswrap.types import Resource, Node, PcsConnector


def _to_bool(value: str) -> bool:
    return 'true' == value


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

    def set_enabled(self, resource_name: str, enabled: bool) -> None:
        command = 'enable'
        if not enabled:
            command = 'disable'
        self._execute(['pcs', 'resource', command, resource_name])

    def _execute(self, cmd: List[str]) -> str:
        process = Popen(cmd,
                        stdin=PIPE,
                        stdout=PIPE,
                        stderr=PIPE,
                        encoding='utf8')
        logging.debug('Issuing CLI command: %s', cmd)
        out, err = process.communicate()
        exit_code = process.returncode
        logging.debug('Finished. Exit code: %d', exit_code)
        if exit_code:
            raise CliException(out, err, exit_code)
        return out


class CliConnector(PcsConnector):
    def __init__(self, executor: CliExecutor = None):
        self.executor: CliExecutor = executor or CliExecutor()

    def get_nodes(self) -> List[Node]:
        b = _to_bool

        def to_node(tag) -> Node:
            return Node(name=tag.attrib['name'],
                        online=b(tag.attrib['online']),
                        shutdown=b(tag.attrib['shutdown']),
                        unclean=b(tag.attrib['unclean']),
                        standby=b(tag.attrib['standby']))

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

    def get_resources(self) -> List[Resource]:
        return self._get_all_resources()

    def get_stonith_resources(self) -> List[Resource]:
        def is_stonith(rsr: Resource) -> bool:
            match = re.match(r'^stonith:', rsr.resource_agent)
            return match is not None

        return [x for x in self._get_all_resources() if is_stonith(x)]

    def disable_resource(self, resource: Resource) -> None:
        self.executor.set_enabled(resource.id, False)

    def enable_resource(self, resource: Resource) -> None:
        self.executor.set_enabled(resource.id, True)

    def _get_all_resources(self) -> List[Resource]:
        xml_str = self.executor.get_full_status_xml()
        xml = self._parse_xml(xml_str)

        def to_resource(tag):
            b = _to_bool
            return Resource(id=tag.attrib['id'],
                            resource_agent=tag.attrib['resource_agent'],
                            role=tag.get('role'),
                            target_role=tag.get('target_role'),
                            active=b(tag.attrib['active']),
                            orphaned=b(tag.attrib['orphaned']),
                            blocked=b(tag.attrib['blocked']),
                            managed=b(tag.attrib['managed']),
                            failed=b(tag.attrib['failed']),
                            failure_ignored=b(tag.attrib['failure_ignored']),
                            nodes_running_on=int(
                                tag.attrib['nodes_running_on']))

        result: List[Resource] = [
            to_resource(tag) for tag in xml.findall('./resources//resource')
        ]
        return result
