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
import os
import yaml
import json
import subprocess
import pytest

from typing import Any, Dict, List


def execute_cmd(cmd: List[str]) -> str:
    process = subprocess.Popen(cmd,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               encoding='utf8')
    out, err = process.communicate()
    if process.returncode:
        raise Exception(
            f'Command {cmd} exited with error code {process.returncode}. '
            f'Command output: {err}')

    return out


def list2dict(
        nodes_data_hctl: List[Dict[str,
                                   Any]]) -> Dict[str, Dict[str, List[str]]]:
    node_info_dict = {}
    for node in nodes_data_hctl:
        node_svc_info: Dict[str, List[str]] = {}
        for service in node['svcs']:
            if not service['name'] in node_svc_info.keys():
                node_svc_info[service['name']] = []
            if (service['status'] == 'started'):
                node_svc_info[service['name']].append(service['status'])
        node_info_dict[node['name']] = node_svc_info

    return node_info_dict


def is_cluster_running() -> bool:
    return os.system('hctl status >/dev/null') == 0


def check_cluster_services(path_to_cdf: str):
    cluster_desc = None
    with open(path_to_cdf, 'r') as stream:
        cluster_desc = yaml.safe_load(stream)
    cmd = ['hctl', 'status', '--json']
    cluster_info = json.loads(execute_cmd(cmd))
    nodes_data_hctl = cluster_info['nodes']

    node_info_dict = list2dict(nodes_data_hctl)
    for node in cluster_desc['nodes']:
        s3_cnt = int(node['m0_clients']['s3'])
        m0ds = node.get('m0_servers', [])
        ios_cnt = 0
        for m0d in m0ds:
            if 'runs_confd' in m0d.keys(
            ) and node_info_dict[node['hostname']]['confd'][0] != 'started':
                logging.error('confd not running on (%s)', node['hostname'])
                return -1

            if m0d['io_disks']['data']:
                if node_info_dict[node['hostname']]['ioservice'] is None:
                    logging.error('No IO service running on (%s)',
                                  node['hostname'])

                if node_info_dict[
                        node['hostname']]['ioservice'][ios_cnt] != 'started':
                    logging.error('Not all IO services running on (%s)',
                                  node['hostname'])
                    return -1
                ios_cnt += 1
        if s3_cnt and len(
                node_info_dict[node['hostname']]['s3server']) != s3_cnt:
            return -1

    return 0

def check_cluster_health():
    try:
        rc = 0
        path_to_cdf = '/var/lib/hare/cluster.yaml'

        if not is_cluster_running():
            logging.error('Cluster is not running. Cluster must be running '
                          'for executing tests')
            return -1
        cluster_status = check_cluster_services(path_to_cdf)
        if cluster_status:
            logging.error('Cluster status reports failure')
            return -1

        logging.info('Tests executed successfully')
        return rc
    except Exception as error:
        logging.error('Error while running Hare  sanity tests (%s)', error)
        return -1


@pytest.mark.sanitytest
def test_sanity():
    logging.info('Executing plan : Sanity')
    ret = check_cluster_health()

    assert ret == 0
