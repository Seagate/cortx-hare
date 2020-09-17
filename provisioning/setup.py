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
import json
import logging
import subprocess
import shutil
from eos.utils.product_features import unsupported_features


def get_data_from_provisioner_cli(method, output_format="json") -> str:
    rc = 0
    try:
        process = subprocess.Popen(
                      ['provisioner', f'{method}', f'--out={output_format}'],
                      shell=True, stdout=subprocess.PIPE)
        process.wait()
        stdout, err = process.communicate()
        rc = process.returncode
    except Exception as e:
        logging.error('Failed to fetch data from prvosioner (%s)', e)
    if rc == 0:
        res = stdout.decode('utf-8')
        if res != "":
            result: str = json.loads(res)['ret']
            return result
    return 'unknown'

def logrotate():
    try:
        setup_info = dict()
        setup_info = get_data_from_provisioner_cli('get_setup_info')
        setup_type = setup_info['storage_type']
        shutil.copyfile(
            f"/opt/seagate/cortx/hare/conf/logrotate/{setup_type}",
	     '/etc/logrotate.d/')
    except Exception as error:
        logging.error('Error setting logrotate values for hare (%s)', error)


class UnsupportedFeatures(argparse.Action):
    def __call__(self, *args):
        try:
            setup_info = dict()
            features_unavailable = []
            path = '/opt/seagate/cortx/hare/conf/setup_info.json'
            hare_features_info = open(path)
            hare_unavailable_features = json.load(hare_features_info)
            self._setup_info  = get_data_from_provisioner_cli('get_setup_info')
            for setup in hare_unavailable_features['setup_types']:
                if setup['name'] == _setup_info['storage_type']:
                    features_unavailable.extend(setup['unsupported_features'])
                    uf_db = unsupported_features.UnsupportedFeaturesDB()
                    uf_db.store_unsupported_features(
                        component_name=str('hare'),
                        features=features_unavailable)
        except Exception as error:
           logging.error('Error reporting hare unsupported features (%s)',
                         error)


def main(argv=None):
    p = argparse.ArgumentParser(description='Configure hare settings')
    p.add_argument('--report-unavailable-features', nargs=0,
                   help='Report unsupported features according to setup type',
                   action=UnsupportedFeatures)
    opts = p.parse_args(argv)
    logrotate()

if __name__ == '__main__':
    main()
