#!/usr/bin/env python3

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

# Setup utility for Hare to configure Hare related settings, e.g. logrotate,
# report unsupported features, etc.

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
import os
import yaml

from cortx.utils.product_features import unsupported_features
from typing import List

def execute(cmd: List[str]) -> str:
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        encoding='utf8')
        out, err = process.communicate()
        if process.returncode:
            raise Exception(f'Command {cmd} exited with error code {process.returncode}. Command output: {err}')

        return out


def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(message)s')


def get_data_from_provisioner_cli(method, output_format='json') -> str:
    try:
        process = subprocess.run(['provisioner', method, f'--out={output_format}'],
                                 check=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 shell=False)
        stdout = process.stdout
        rc = process.returncode
    except Exception as e:
        logging.error('Failed to fetch data from provisioner (%s)', e)
        return 'unknown'
    if rc != 0:
        return 'unknown'
    res = stdout.decode('utf-8')
    return json.loads(res)['ret'] if res else 'unknown'


def logrotate_config():
    try:
        setup_info = get_data_from_provisioner_cli('get_setup_info')
        if setup_info != 'unknown':
            server_type = setup_info['server_type']
            shutil.copyfile(f'/opt/seagate/cortx/hare/conf/logrotate/{server_type}',
                            '/etc/logrotate.d/hare')
    except Exception as error:
        logging.error('Error setting logrotate values for hare (%s)', error)


def _report_unsupported_features(features_unavailable):
    uf_db = unsupported_features.UnsupportedFeaturesDB()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(uf_db.store_unsupported_features('hare',
                            features_unavailable))


class UnsupportedFeatures(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            features_unavailable = []
            path = '/opt/seagate/cortx/hare/conf/setup_info.json'
            with open(path) as hare_features_info:
                hare_unavailable_features = json.load(hare_features_info)
                setup_info = get_data_from_provisioner_cli('get_setup_info')
                if setup_info != 'unknown':
                    for setup in hare_unavailable_features['setup_types']:
                        if setup['server_type'] == setup_info['server_type']:
                            features_unavailable.extend(
                                setup['unsupported_features'])
                            _report_unsupported_features(features_unavailable)
        except Exception as error:
            logging.error('Error reporting hare unsupported features (%s)',
                          error)

class PostInstall(argparse.Action):
    """
    Assumption: motr, hare, consul, cortx-py-utils and cortx-s3server rpms are already installed
    Approach: Will use 'rpm -qa | grep -q <rpm_name>' command to check if rpm is installed
    """
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            if checkRpm('cortx-motr') != 0:
                logging.error('\'cortx-motr\' is not installed')
                exit(-1)
            if checkRpm('consul') != 0:
                logging.error('\'consul\' is not installed')
                exit(-1)
            if checkRpm('cortx-hare') != 0:
                logging.error('\'cortx-hare\' is not installed')
                exit(-1)
            if checkRpm('cortx-py-utils') != 0:
                logging.error('\'cortx-py-utils\' is not installed')
                exit(-1)
            if checkRpm('cortx-s3server') != 0:
                logging.warning('\'cortx-s3server\' is not installed')
        except Exception as error:
            logging.error('Error while checking installed rpms (%s)',
                          error)
            exit(-1)

class Init(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            if not is_cluster_running() and bootstrap_cluster() != 0:
                logging.error('Failed to bootstrap the custer')
                exit(1)

            while is_cluster_running():
                shutdown_cluster()

        except Exception as error:
            logging.error('Error while initializing the cluster (%s)',
                          error)
            exit(-1)

class Test(argparse.Action):
    """
    Read CDF file and compare fields with output of 'hctl status'
    Will start the cluster(and shutdown before exiting) if not already started
    """
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            if not is_cluster_running() and bootstrap_cluster() != 0:
                logging.error('Failed to bootstrap the cluster')
                exit(-1)

            cluster_status = check_cluster_status()

            while is_cluster_running():
                shutdown_cluster()

            if cluster_status:
                logging.error('Cluster status reports failure')
                exit(-1)

        except Exception as error:
            logging.error('Error while checking cluster status (%s)',
                          error)
            exit(-1)

class SupportBundle(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            # Default target directory is /tmp/hare
            if os.system('hctl reportbug') != 0:
                logging.error('Failed to generate support bundle')
                exit(-1)
        except Exception as error:
            logging.error('Error while generating support bundle (%s)',
                          error)
            exit(-1)

class Cleanup(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            exit(0)
        except Exception as error:
            logging.error('Failed to perform cleanup (%s)',
                          error)
            exit(-1)

def checkRpm(rpm_name):
    rpm_list = subprocess.Popen(["rpm", "-qa"],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env={},
                                encoding='utf8')
    rpm_search = subprocess.Popen(["grep", "-q", rpm_name],
                                  stdin=rpm_list.stdout,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  env={},
                                  encoding='utf8')
    out, err = rpm_search.communicate()
    logging.debug("Output: {}".format(out))
    logging.debug("stderr: {}".format(err))

    return rpm_search.returncode


def is_cluster_running() -> bool:
    return os.system('hctl status >/dev/null') == 0


def bootstrap_cluster():
    return os.system('hctl bootstrap --mkfs /var/lib/hare/cluster.yaml')


def shutdown_cluster():
    return os.system('hctl shutdown')


def list2dict(nodes_data_hctl: list) -> dict:
    node_info_dict = {}
    for node in nodes_data_hctl:
        node_svc_info = {}
        for service in node['svcs']:
            if not service['name'] in node_svc_info.keys():
                node_svc_info[service['name']] = []
            if (service['status'] == 'started'):
                node_svc_info[service['name']].append(service['status'])
        node_info_dict[node['name']] = node_svc_info

    return node_info_dict


def check_cluster_status():
    cluster_desc = None
    with open("/var/lib/hare/cluster.yaml", 'r') as stream:
        cluster_desc = yaml.safe_load(stream)
    cmd = ['hctl', 'status', '--json']
    cluster_info = json.loads(execute(cmd))
    nodes_data_hctl = cluster_info['nodes']

    node_info_dict = list2dict(nodes_data_hctl)
    for node in cluster_desc['nodes']:
        m0client_s3_cnt = node['m0_clients']['s3']
        m0ds = node.get('m0_servers', [])
        ios_cnt = 0
        for m0d in m0ds:
            if ('runs_confd' in m0d.keys() and
                (node_info_dict[node['hostname']]['confd'][0] != 'started')):
                return -1
            if m0d['io_disks']['data']:
                if node_info_dict[node['hostname']]['ioservice'][ios_cnt] != 'started':
                  return -1
                ios_cnt += 1
        if (m0client_s3_cnt > 0 and
            len(node_info_dict[node['hostname']]['s3server']) != m0client_s3_cnt):
                return -1

    return 0


def main():
    p = argparse.ArgumentParser(description='Configure hare settings')
    p.add_argument('--report-unavailable-features',
                   nargs=0,
                   help='Report unsupported features according to setup type',
                   action=UnsupportedFeatures)
    p.add_argument('--post_install',
                   nargs=0,
                   help='Perform post installation checks',
                   action=PostInstall)
    p.add_argument('--init',
                   nargs=0,
                   help='Perform component initialization',
                   action=Init)
    p.add_argument('--test',
                   nargs=0,
                   help='Testing cluster status',
                   action=Test)
    p.add_argument('--support_bundle',
                   nargs=0,
                   help='Testing cluster status',
                   action=SupportBundle)
    p.add_argument('--reset','--cleanup',
                   nargs=0,
                   help='Reset/cleanup step',
                   action=Cleanup)

    setup_logging()

    p.parse_args()

    # Below function assumes that provisioner is installed.
    # Might need to revisit if this assumption is not true always
    logrotate_config()


if __name__ == '__main__':
    main()
