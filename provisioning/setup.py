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

from eos.utils.product_features import unsupported_features


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
                        if setup['name'] == setup_info['server_type']:
                            features_unavailable.extend(
                                setup['unsupported_features'])
                            _report_unsupported_features(features_unavailable)
        except Exception as error:
            logging.error('Error reporting hare unsupported features (%s)',
                          error)


def main(argv=None):
    p = argparse.ArgumentParser(description='Configure hare settings')
    p.add_argument('--report-unavailable-features',
                   nargs=0,
                   help='Report unsupported features according to setup type',
                   action=UnsupportedFeatures)
    p.parse_args(argv)
    logrotate_config()


if __name__ == '__main__':
    main()
