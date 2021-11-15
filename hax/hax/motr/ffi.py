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

import ctypes as c
import logging
import os
import platform

from typing import Optional
from hax.types import FidStruct, HaNoteStruct, Uint128Struct

LOG = logging.getLogger('hax')

py_func_proto = c.PYFUNCTYPE(None, c.c_void_p)


def make_c_str(str_val: Optional[str]) -> Optional[c.c_char_p]:
    if str_val is None:
        return None
    byte_str = str_val.encode('utf-8')
    return c.c_char_p(byte_str)


def make_array(ctr, some_list):
    # [KN] This is just an awkward syntax to tell ctypes
    # that we're willing to pass a C array of type described by ctr
    #
    # Example: self._make_arr(c.c_char_p, ['12'])
    arr_type = ctr * len(some_list)
    return arr_type(*some_list)


class HaxFFI:
    def __init__(self):
        dirname = os.path.dirname(os.path.abspath(__file__))
        arch = platform.machine()
        lib_path = f'{dirname}/../../libhax.cpython-36m-{arch}-linux-gnu.so'
        LOG.debug('Loading library from path: %s', lib_path)
        lib = c.cdll.LoadLibrary(lib_path)
        lib.init_motr_api.argtypes = [c.py_object, c.c_char_p]
        lib.init_motr_api.restype = c.c_void_p

        lib.start.argtypes = [
            c.c_void_p, c.c_char_p,
            c.POINTER(FidStruct),
            c.POINTER(FidStruct),
            c.POINTER(FidStruct)
        ]
        lib.start.restype = c.c_int

        self.init_motr_api = lib.init_motr_api
        self.start = lib.start

        lib.start_rconfc.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.start_rconfc.restype = c.c_int
        self.start_rconfc = lib.start_rconfc
        self.motr_stop = py_func_proto(('motr_api_stop', lib))
        self.motr_fini = py_func_proto(('motr_api_fini', lib))

        lib.stop_rconfc.argtypes = [c.c_void_p]
        lib.stop_rconfc.restype = c.c_int
        self.stop_rconfc = lib.stop_rconfc

        lib.m0_ha_entrypoint_reply_send.argtypes = [
            c.c_void_p,  # unsigned long long epr
            c.POINTER(Uint128Struct),  # const struct m0_uint128    *req_id
            c.c_int,  # int rc
            c.c_uint32,  # uint32_t confd_nr
            c.POINTER(FidStruct),  #
            c.POINTER(c.c_char_p),  # const char **confd_eps_data
            c.c_uint32,  # uint32_t                    confd_quorum
            c.POINTER(FidStruct),  # const struct m0_fid        *rm_fid
            c.c_char_p  # const char *rm_eps
        ]
        self.entrypoint_reply = lib.m0_ha_entrypoint_reply_send

        lib.m0_ha_notify.argtypes = [
            c.c_void_p,  # unsigned long long ctx
            c.POINTER(HaNoteStruct),  # struct m0_ha_note *notes
            c.c_uint32,  # uint32_t nr_notes
        ]
        lib.m0_ha_notify.restype = c.py_object
        self.ha_broadcast = lib.m0_ha_notify

        lib.m0_ha_notify_hax_only.argtypes = [
            c.c_void_p,  # unsigned long long ctx
            c.POINTER(HaNoteStruct),  # struct m0_ha_note *notes
            c.c_uint32,  # uint32_t nr_notes
            c.c_char_p  # const char *hax_ep
        ]
        lib.m0_ha_notify_hax_only.restype = c.py_object
        self.ha_broadcast_hax_only = lib.m0_ha_notify_hax_only

        lib.m0_ha_nvec_reply_send.argtypes = [
            c.c_void_p,  # unsigned long long  hax_msg
            c.POINTER(HaNoteStruct),  # struct m0_ha_note *notes
            c.c_uint32  # uint32_t nr_notes
        ]
        self.ha_nvec_reply = lib.m0_ha_nvec_reply_send

        lib.m0_hax_stop.argtypes = [
            c.c_void_p,  # unsigned long long ctx
            c.POINTER(FidStruct),  # const struct m0_fid *process_fid
            c.c_char_p  # const char *hax_ep
        ]
        lib.m0_hax_stop.restype = c.py_object
        self.hax_stop = lib.m0_hax_stop

        lib.m0_hax_link_stopped.argtypes = [
            c.c_void_p,  # unsigned long long  hax_msg
            c.c_char_p  # const char *hax_ep
        ]
        self.hax_link_stopped = lib.m0_hax_link_stopped

        lib.m0_ha_filesystem_stats_fetch.argtypes = [c.c_void_p]
        lib.m0_ha_filesystem_stats_fetch.restype = c.py_object
        self.filesystem_stats_fetch = lib.m0_ha_filesystem_stats_fetch

        lib.repair_status.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.repair_status.restype = c.py_object
        self.repair_status = lib.repair_status

        lib.rebalance_status.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.rebalance_status.restype = c.py_object
        self.rebalance_status = lib.rebalance_status

        lib.start_repair.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.start_repair.restype = c.c_int
        self.start_repair = lib.start_repair

        lib.start_rebalance.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.start_rebalance.restype = c.c_int
        self.start_rebalance = lib.start_rebalance

        lib.stop_repair.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.stop_repair.restype = c.c_int
        self.stop_repair = lib.stop_repair

        lib.stop_rebalance.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.stop_rebalance.restype = c.c_int
        self.stop_rebalance = lib.stop_rebalance

        lib.pause_repair.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.pause_repair.restype = c.c_int
        self.pause_repair = lib.pause_repair

        lib.pause_rebalance.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.pause_rebalance.restype = c.c_int
        self.pause_rebalance = lib.pause_rebalance

        lib.resume_repair.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.resume_repair.restype = c.c_int
        self.resume_repair = lib.resume_repair

        lib.resume_rebalance.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.resume_rebalance.restype = c.c_int
        self.resume_rebalance = lib.resume_rebalance
