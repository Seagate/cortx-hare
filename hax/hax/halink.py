import ctypes as c
import logging
import threading
import os
from hax.server import Message
from hax.types import Fid, FidStruct, Uint128Struct
from hax.util import ConsulUtil

prot2 = c.PYFUNCTYPE(None, c.c_void_p)


def log_exception(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logging.exception("error")

    return wrapper


class HaLink(object):
    def __init__(self, node_uuid="", queue=None, rm_fid=None):
        dirname = os.path.dirname(os.path.abspath(__file__))
        lib_path = '{}/../libhax.so'.format(dirname)
        logging.debug('Loading library from path: {}'.format(lib_path))
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

        self.__init_halink = lib.init_halink
        self.__test = prot2(('test', lib))
        self.__start = lib.start
        self.__destroy = prot2(('destroy_halink', lib))

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
        self.__entrypoint_reply = lib.m0_ha_entrypoint_reply_send

        self._ha_ctx = self.__init_halink(self, self._c_str(node_uuid))
        self.queue = queue
        self.rm_fid = rm_fid
        # if not self._ha_ctx:
        # raise RuntimeError("Could not initialize ha_link")

    def start(self, rpc_endpoint: str, process: Fid, ha_service: Fid,
              rm_service: Fid):
        tname = threading.currentThread().getName()
        logging.info('Start method is invoked from thread {}'.format(tname))
        self.__start(self._ha_ctx, self._c_str(rpc_endpoint), process.to_c(),
                     ha_service.to_c(), rm_service.to_c())

    def _c_str(self, str_val: str) -> c.c_char_p:
        if not str_val:
            return None
        byte_str = str_val.encode('utf-8')
        return c.c_char_p(byte_str)

    # TODO remove me
    def test(self):
        tname = threading.currentThread().getName()
        logging.info('Test method is invoked from thread {}'.format(tname))
        self.__test(self._ha_ctx)
        # TODO call m0d from here

    # TODO remove me
    def test_cb(self, data):
        logging.debug("Sending the test message to the queue")
        # TODO the actual data must be put here
        self.queue.put(Message(data))
        logging.debug("The locality thread is free now")

    @log_exception
    def _entrypoint_request_cb(self, reply_context, req_id,
                               remote_rpc_endpoint, process_fid, git_rev, pid,
                               is_first_request):
        logging.debug(
            "Started processing entrypoint request from remote eps = '{}', process_fid = {}"
            .format(remote_rpc_endpoint, str(process_fid)))

        prov = ConsulUtil()
        sess = prov.get_leader_session()
        principal_rm = prov.get_session_node(sess)
        confds = prov.get_confd_list()
        tname = threading.currentThread().getName()
        logging.info('in _entrypoint_request_cb'.format(tname))

        rc_quorum = int(len(confds) / 2 + 1)

        rm_eps = None
        for cnf in confds:
            if cnf.get('node') == principal_rm:
                rm_eps = cnf.get('address')
                break
        confd_fids = list(map(lambda x: x.get('fid').to_c(), confds))
        confd_eps = list(map(lambda x: self._c_str(x.get('address')), confds))

        make_array = self._make_arr

        logging.debug("Pasing the entrypoint reply to hax.c layer")
        self.__entrypoint_reply(reply_context, req_id.to_c(), 0, len(confds),
                                make_array(FidStruct, confd_fids),
                                make_array(c.c_char_p, confd_eps), rc_quorum,
                                self.rm_fid.to_c(), self._c_str(rm_eps))
        logging.debug(
            "Entrypoint request replied, mero's locality thread is free now")

    def _make_arr(self, ctr, some_list):
        # [KN] This is just an awkward syntax to tell ctypes
        # that we're willing to pass a C array of type described by ctr
        #
        # Example: self._make_arr(c.c_char_p, ['12'])
        arr_type = ctr * len(some_list)
        return arr_type(*some_list)

    def close(self):
        logging.debug("Destructing ha_link")
        self.__destroy(self._ha_ctx)
        self._ha_ctx = 0
        logging.debug("ha_link destroyed. Bye!")
