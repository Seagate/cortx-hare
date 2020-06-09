import ctypes as c
import logging
import os

from hax.types import FidStruct, HaNoteStruct, Uint128Struct

py_func_proto = c.PYFUNCTYPE(None, c.c_void_p)


def make_c_str(str_val: str) -> c.c_char_p:
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
        lib_path = f'{dirname}/../libhax.cpython-36m-x86_64-linux-gnu.so'
        logging.debug('Loading library from path: %s', lib_path)
        lib = c.cdll.LoadLibrary(lib_path)
        lib.init_halink.argtypes = [c.py_object, c.c_char_p]
        lib.init_halink.restype = c.c_void_p

        lib.start.argtypes = [
            c.c_void_p, c.c_char_p,
            c.POINTER(FidStruct),
            c.POINTER(FidStruct),
            c.POINTER(FidStruct)
        ]
        lib.start.restype = c.c_int

        self.init_halink = lib.init_halink
        self.start = lib.start

        lib.start_rconfc.argtypes = [c.c_void_p, c.POINTER(FidStruct)]
        lib.start_rconfc.restype = c.c_int
        self.start_rconfc = lib.start_rconfc
        self.destroy = py_func_proto(('destroy_halink', lib))

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
            c.c_uint32  # uint32_t nr_notes
        ]
        self.ha_broadcast = lib.m0_ha_notify

        lib.m0_ha_nvec_reply_send.argtypes = [
            c.c_void_p,  # unsigned long long  hax_msg
            c.POINTER(HaNoteStruct),  # struct m0_ha_note *notes
            c.c_uint32  # uint32_t nr_notes
        ]
        self.ha_nvec_reply = lib.m0_ha_nvec_reply_send

        lib.adopt_motr_thread.argtypes = []
        lib.adopt_motr_thread.restype = c.c_int
        self.adopt_motr_thread = lib.adopt_motr_thread
        self.shun_motr_thread = lib.shun_motr_thread

        lib.m0_ha_filesystem_stats_fetch.argtypes = [c.c_void_p]
        lib.m0_ha_filesystem_stats_fetch.restype = c.py_object
        self.filesystem_stats_fetch = lib.m0_ha_filesystem_stats_fetch
