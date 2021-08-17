#!/usr/bin/python
# -*- coding: utf-8 -*-
#
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

"""
Hare test suite for bootstrap shutdown on single node.
"""

import logging
import pytest

from datetime import datetime

from commons import commands as cmds
from provisioning.miniprov.hare_mp.main import execute, check_cluster_status,\
    is_cluster_running, bootstrap_cluster

LOGGER = logging.getLogger(__name__)


class TestHareBootstrapShutdown:
    """
    Test suite for hare bootstrap shutdown on single node.
    """

    @classmethod
    def setup_class(self, args):
        """
        Setup operations for the test file.
        """
        LOGGER.info("STARTED: Setup Module operations")
        self.loop_count = int(args.dev[0])
        self.now = datetime.now()
        self.cdf_file = str(args.file[0])

        LOGGER.info("Done: Setup module operations")

    def setup_method(self):
        """
        This function will be invoked prior to each test case.
        """
        LOGGER.info("STARTED: Setup Operations")

        logging.info('Test started on Host: {}'
                     .format(execute(['hostname'])))
        logging.info('Check that all services are up in PCS.')

        resp = execute(cmds.pcs_status)
        logging.info('PCS status: %s', resp)

        if 'cluster is not currently' in resp:
            return

        logging.info('Make Node ready for testing, by stopping the cluster.')
        resp = execute(cmds.cluster_stop)
        logging.info('Cluster Stopped: %s', resp)
        if 'Cluster stop is in progress' not in resp:
            logging.error('Cluster is in progress.')

    def teardown_method(self):
        """
        This function will be invoked after each test function in the module.
        """
        LOGGER.info("STARTED: Teardown Operations.")
        logging.info('Start the Cluster')
        resp = execute(cmds.cluster_start)
        logging.info('cluster status: %s', resp)
        if 'Cluster start operation performed' not in resp:
            logging.error('Cluster not yet started.')

        logging.info('PCS: Check all services are up.')
        resp = execute(cmds.pcs_status)
        logging.info('PCS status: %s', resp)
        if 'stopped' not in resp:
            logging.error('Some services are not up.')

        logging.info('hctl: Check that all the services are started.')
        cluster_sts = check_cluster_status(self.cdf_file)
        if cluster_sts:
            resp = execute(['journalctl', '--since', self.date_time, '>',
                            self.jlog])
            logging.info('created journal log: %s', self.jlog)
            raise Exception('hctl status reports failure.')

        logging.info('Successfully performed cleanup after testing')
        LOGGER.info("All nodes are online and PCS looks clean.")
        LOGGER.info("ENDED: Teardown Operations.")

    @pytest.mark.hare
    @pytest.mark.tags("EOS-22149")
    def test_single_nodes_bootstrap_shutdown(self):
        """
        Test hare init in loop on single node .
        """

        if is_cluster_running():
            execute(cmds.hctl_status)
            # if exit_code:
            #     if 'Cluster is not running' not in out:
            #         resp = execute(hctl_shutdown)
            #         logging.info('hctl shutdown: %s', resp)
            #         if is_cluster_running():
            #             raise Exception('After shutdown, hctl is running.')
            #     else:
            #         raise Exception(
            #         f'Command hctl status exited with error code {exit_code}'
            #             f'Command output: {err}')
            # else:
            #     raise Exception('Fail to control cluster, exit the test.')

        logging.info('-------Starting BOOTSTRAP-SHUTDOWN in LOOP-------')
        for count in range(self.loop_count):
            logging.info('Loop count# {}'.format(count + 1))
            self.now = datetime.now()  # current date and time
            self.date_time = self.now.strftime("%Y-%m-%d %H:%M:%S")
            self.jlog = '~/journal_ctrl_' + \
                        self.now.strftime('%Y_%m_%d_%H%M%S') + '.log'

            logging.info('Start hctl Bootstrap')
            resp = bootstrap_cluster(self.cdf_file, True)
            if resp:
                resp = execute(['journalctl', '--since', self.date_time, '>',
                                self.jlog])
                logging.info('created journal log: %s', self.jlog)
                raise Exception('Failed to bootstrap.')

            logging.info('Check that all the services are up in hctl.')
            if is_cluster_running():
                logging.info('hctl is running.')
                cluster_sts = check_cluster_status(self.cdf_file)
                if cluster_sts:
                    resp = execute(
                        ['journalctl', '--since', self.date_time, '>',
                         self.jlog])
                    logging.info('created journal log: %s', self.jlog)
                    raise Exception('hctl status reports failure.')
            else:
                resp = execute(['journalctl', '--since', self.date_time, '>',
                                self.jlog])
                logging.info('created journal log: %s', self.jlog)
                raise Exception('After Bootstrap, hctl is not running.')

            logging.info('Shutdown the cluster.')
            resp = execute(cmds.hctl_shutdown)
            logging.info('hctl shutdown: %s', resp)
            if is_cluster_running():
                resp = execute(['journalctl', '--since', self.date_time, '>',
                                self.jlog])
                logging.info('created journal log: %s', self.jlog)
                raise Exception('After shutdown, hctl is running.')

        # test_hare_postreq(str(args.file[0]), date_time, jlog)
