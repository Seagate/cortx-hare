import logging
import re
from subprocess import PIPE, Popen
from typing import Any, Dict, List, Match, Optional, Tuple

import defusedxml.ElementTree as ET

from pcswrap.exception import CliException, PcsNoStatusException
from pcswrap.types import Node, PcsConnector, Resource, StonithResource


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

    def authorize(self, username: str, password: str) -> None:
        self._execute(
            ['pcs', 'client', 'local-auth', '-u', username, '-p', password])

    def get_stonith_resource_details(self, resource_name: str) -> str:
        return self._execute(['pcs', 'stonith', 'show', resource_name])

    def shutdown_by_ipmi(self, node_name: str, username: str, password: str,
                         ipaddr: str):
        return self._execute([
            'ipmitool', '-H', ipaddr, '-v', '-I', 'lanplus', '-U', username,
            '-P', password, 'chassis', 'power', 'off'
        ])

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


class StonithParser:
    def _parse_kv(self, text: str) -> Dict[str, str]:
        def to_pair(s: str) -> Tuple[str, str]:
            match = re.match(r'^\s*([^=]*)=([^ ]*)$', s)
            assert match
            return (match.group(1), match.group(2))

        pairs = [to_pair(t) for t in text.split(' ')]
        return {key: val for (key, val) in pairs}

    def parse(self, raw_text: str) -> StonithResource:
        lines = raw_text.splitlines()

        def apply_re(regex: str, text_to_match: str) -> Match:
            match = re.match(regex, text_to_match)
            if not match:
                raise RuntimeError(
                    'Output of "pcs stonith show <name>" was not understood')
            return match

        def get_line() -> str:
            while True:
                if not lines:
                    raise StopIteration()
                result = lines.pop(0).strip()
                if result:
                    return result

        # First non-empty line: Resource: <ID> (class=<ID> type=fence_ipmilan)
        s = get_line()
        match = apply_re(
            r'^\s*Resource: ([^ ]+) \(class=([^ ]+) type=([^\)]+).*$', s)
        klass = match.group(2)
        typename = match.group(3)
        assert typename == 'fence_ipmilan'

        # Second non-empty line: Attributes: [key=value]( [key=value])*
        match = apply_re(r'^\s*Attributes: (.*)$', get_line())
        attr_dict = self._parse_kv(match.group(1))
        return StonithResource(klass=klass,
                               typename=typename,
                               pcmk_host_list=attr_dict['pcmk_host_list'],
                               ipaddr=attr_dict['ipaddr'],
                               login=attr_dict['login'],
                               passwd=attr_dict['passwd'])


class CliConnector(PcsConnector):
    def __init__(self, executor: CliExecutor = None):
        self.executor: CliExecutor = executor or CliExecutor()

    def get_nodes(self) -> List[Node]:
        b = _to_bool

        def to_node(tag) -> Node:
            return Node(name=tag.attrib['name'],
                        online=b(tag.attrib['online']),
                        unclean=b(tag.attrib['unclean']),
                        standby=b(tag.attrib['standby']),
                        resources_running=int(tag.attrib['resources_running']))

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
        raise PcsNoStatusException('Failed to find cluster name: pcs status '
                                   'command output was not recognized')

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

    def get_stonith_resource_details(self,
                                     resource_name: str) -> StonithResource:
        raw = self.executor.get_stonith_resource_details(resource_name)
        return StonithParser().parse(raw)

    def get_fence_resource_for_node(
            self, node_name: str) -> Optional[StonithResource]:
        for res in self.get_stonith_resources():
            details = self.get_stonith_resource_details(res.id)
            if details.pcmk_host_list == node_name:
                return details
        return None

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

    def ensure_authorized(self) -> None:
        c = self.get_credentials()
        if not c:
            logging.debug('Skipping pcsd authentication as no credentials '
                          'were provided')
            return
        self.executor.authorize(c.username, c.password)

    def manual_shutdown_node(self, node_name: str) -> None:
        resource = self.get_fence_resource_for_node(node_name)
        if not resource:
            raise RuntimeError(
                f'No stonith resource is found for node {node_name}. '
                'It is no other way to extract IPMI parameters to '
                'shutdown the node')

        self.executor.shutdown_by_ipmi(node_name, resource.login,
                                       resource.passwd, resource.ipaddr)

    def ensure_shutdown_possible(self, node_name: str) -> None:
        resource = self.get_fence_resource_for_node(node_name)
        if not resource:
            raise RuntimeError(
                f'No stonith resource is found for node {node_name}.')

    def get_eligible_resource_count(self) -> int:
        xml_str = self.executor.get_full_status_xml()
        xml = self._parse_xml(xml_str)
        tag = xml.find('./summary/resources_configured')
        total = int(tag.attrib['number'])
        disabled = int(tag.attrib['disabled'])
        blocked = int(tag.attrib['blocked'])
        return total - disabled - blocked
