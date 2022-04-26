# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
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

# flake8: noqa
import logging
import unittest
from unittest.mock import Mock

from hax.log import TRACE
from hax.motr import Motr
from hax.types import (Fid, HaNoteStruct, HAState,
                               ObjHealth, m0HaObjState)
from hax.util import (FidWithType, PutKV, ConsulUtil)
from hax.consul.cache import InvocationCache

def _has_failed_note(notes, fid):
    for n in notes:
        if (n.no_state == ObjHealth.FAILED.to_ha_note_status()
                and n.no_id.f_container == fid.container
                and n.no_id.f_key == fid.key):
            return True
    return False


LOG = logging.getLogger('hax')

class TestFailure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # It seems like when unittest is invoked from setup.py,
        # some default logging configuration is already applied;
        # invoking setup_logging() will make the log messages to appear twice.
        logging.addLevelName(TRACE, 'TRACE')
        logging.getLogger('hax').setLevel(TRACE)

    def test_process_failure(self):
        consul_util = ConsulUtil()
        consul_cache = InvocationCache()
        ffi = Mock(spec=['init_motr_api'])
        motr = Motr(ffi, None, None, consul_util)

        # Setup for the test: notification of a process failure
        # - failure here is an ios service and a disk
        # - dummy Consul reports all processes on the node are failed
        # - expect the node, enclosure, controller, drive,
        #   process, and service to all be marked as failed
        #
        # Static names and fids for the setup are given here.
        node_name = 'testnode'

        hax_fid = Fid(0x7200000000000001, 0x6)
        site_fid = Fid(0x5300000000000001, 0x1)
        rack_fid = Fid(0x6100000000000001, 0x2)
        node_fid = Fid(0x6e00000000000001, 0x3)
        encl_fid = Fid(0x6500000000000001, 0x4)
        ctrl_fid = Fid(0x6300000000000001, 0x5)
        process_fid = Fid(0x7200000000000001, 0x15)
        service_fid = Fid(0x7300000000000001, 0xe)
        service_fid_typed = FidWithType(fid=service_fid, service_type='ios')
        drive_fid = Fid(0x6b00000000000001, 0x11)
        ctrl_path = 'm0conf/sites/{}/racks/{}/encls/{}/ctrls/{}'.format(
                site_fid, rack_fid, encl_fid, ctrl_fid)
        ctrl_state = '{"state": "M0_NC_FAILED"}'

        # Set mock return values for the necessary Consul calls
        motr._is_mkfs = Mock(return_value=False)
        consul_util.get_hax_fid = Mock(return_value=hax_fid)
        consul_util.is_proc_client = Mock(return_value=False)
        consul_util.get_services_by_parent_process = Mock(return_value=[service_fid_typed])
        consul_util.get_disks_by_parent_process = Mock(return_value=[drive_fid])
        consul_util.get_process_node = Mock(return_value=node_name)
        consul_util.get_node_name_by_fid = Mock(return_value=node_name)
        consul_util.get_node_fid = Mock(return_value=node_fid)
        consul_util.get_node_encl_fid = Mock(return_value=encl_fid)
        consul_util.get_node_ctrl_fids = Mock(return_value=[ctrl_fid])

        # These failure indications are here to trigger specific code paths for
        # node failure. Additional tests can cover different scenarios (e.g.
        # drive failure but node still up), which will set differernt results
        # for these calls.
        consul_util.all_io_services_failed = Mock(return_value=True)
        consul_util.get_sdev_state = Mock(return_value=HaNoteStruct.M0_NC_FAILED)
        consul_util.get_ctrl_state = Mock(return_value=m0HaObjState.M0_NC_FAILED)
        consul_util.get_ctrl_state_updates = Mock(return_value=[PutKV(
            key=ctrl_path, value=ctrl_state)])

        # We'll use these mocks to check that expected updates are happening.
        consul_util.update_drive_state = Mock()
        consul_util.set_process_state = Mock()
        consul_util.set_node_state = Mock()
        consul_util.set_encl_state = Mock()
        motr._ha_broadcast=Mock()
        motr._write_updates=Mock()

        # Send the mock event.
        motr.broadcast_ha_states(
                [HAState(
                    fid=process_fid,
                    status=ObjHealth.FAILED)],
                notify_devices=True,
                broadcast_hax_only=False,
                kv_cache=consul_cache)

        # ConsulUtil is responsible for the actual KV updates, just check
        # here that the appropriate util function is called for each
        # component.
        consul_util.update_drive_state.assert_called_with(
                [drive_fid],
                ObjHealth.OFFLINE,
                device_event=False)
        consul_util.set_process_state.assert_called_with(
                process_fid,
                ObjHealth.FAILED)
        consul_util.set_node_state.assert_called_with(
                node_fid,
                ObjHealth.FAILED)
        consul_util.set_encl_state.assert_called_with(
                encl_fid, ObjHealth.FAILED, kv_cache=consul_cache)
        # This KV update is batched, so the check looks different.
        motr._write_updates.assert_any_call(
                [PutKV(key=ctrl_path, value=ctrl_state)],
                consul_cache)

        # Check hax broadcast. We should see states updated to FAILED.
        broadcast_list = motr._ha_broadcast.call_args[0][0]
        self.assertTrue(_has_failed_note(broadcast_list, node_fid))
        self.assertTrue(_has_failed_note(broadcast_list, encl_fid))
        self.assertTrue(_has_failed_note(broadcast_list, ctrl_fid))
        self.assertTrue(_has_failed_note(broadcast_list, process_fid))
        self.assertTrue(_has_failed_note(broadcast_list, service_fid))
        self.assertTrue(_has_failed_note(broadcast_list, drive_fid))
