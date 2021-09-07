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

import argparse
import logging
import sys

from helper.generate_sysconf import Generator
from hax.types import Fid, ObjT


def _setup_logging():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s [%(levelname)s] %(message)s')


def parse_opts(argv):

    p = argparse.ArgumentParser(
        description='Generates configuration files for consul-agent, motr '
        'and s3 services.',
        usage='%(prog)s node [OPTION]')

    p.add_argument(
        'node',
        help='Node-name of the services whose config files are generated.',
        type=str,
        action='store')
    p.add_argument(
        '--hare-conf-dir',
        help='Path to hare config directory.',
        required=True,
        type=str,
        action='store')
    p.add_argument(
        '--motr-conf-dir',
        '-m',
        help='Path to motr config directory.',
        type=str,
        action='store')
    p.add_argument(
        '--s3-conf-dir',
        '-s',
        help='Path to S3 config directory.',
        type=str,
        action='store')
    p.add_argument(
        '--kv-file',
        help='Hare-Motr configuration key values file path.',
        type=str,
        action='store')
    p.add_argument(
        '--fid',
        help='Returns only the fids of the service for the current nodes '
        'in cluster. '
        'List of service fids - "hax", "confd", "ios", "s3". '
        'No configuration files are created.',
        type=str,
        action='store')

    return p.parse_args(argv)


def main(argv=None):
    opts = parse_opts(argv)
    _setup_logging()
    try:
        generator = Generator(opts.node, opts.hare_conf_dir,
                              kv_file=opts.kv_file)
        if opts.fid:
            logging.disable(logging.DEBUG)
            IDs = generator.get_all_svc_ids()
            id_map = {
                'hax': IDs['HAX_ID'],
                'confd': IDs['CONFD_IDs'],
                'ios': IDs['IOS_IDs'],
                's3': IDs['S3_IDs']
            }
            print([Fid(ObjT.PROCESS.value, int(x))
                   for x in id_map[opts.fid]])
            return
        if not opts.motr_conf_dir or not opts.s3_conf_dir:
            raise Exception('--motr-conf-dir and --s3-conf-dir arguments'
                            ' are required.')
        generator.generate_sysconfig(opts.motr_conf_dir, opts.s3_conf_dir)

        generator.update_consul_conf()

    except Exception as e:
        logging.error('Exiting due to a failure: %s', e)
        sys.exit(-1)


if __name__ == '__main__':
    sys.exit(main())
