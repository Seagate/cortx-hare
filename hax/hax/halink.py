import ctypes as c
import logging
import threading
import os
from hax.server import Message
from hax.types import Fid, FidStruct

dirname = os.path.dirname(os.path.abspath(__file__))
lib_path = '{}/../hax.so'.format(dirname)
lib = c.cdll.LoadLibrary(lib_path)

prototype = c.PYFUNCTYPE(c.c_ulonglong, c.py_object)
prot2 = c.PYFUNCTYPE(None, c.c_void_p)

_init_halink = prototype(('init_halink', lib))
_test = prot2(('test', lib))
lib.init_halink.argtypes = [c.py_object, c.c_char_p]
lib.init_halink.restype = c.c_void_p

lib.start.argtypes = [
    c.c_void_p, c.c_char_p,
    c.POINTER(FidStruct),
    c.POINTER(FidStruct),
    c.POINTER(FidStruct)
]
lib.start.restype = c.c_int


class HaLink(object):
    def __init__(self, node_uuid="", queue=None):
        self._ha_ctx = lib.init_halink(self, self._c_str(node_uuid))
        self.queue = queue
        # if not self._ha_ctx:
        # raise RuntimeError("Could not initialize ha_link")

    def start(self, rpc_endpoint: str, process: Fid, ha_service: Fid,
              rm_service: Fid):
        # import pudb; pudb.set_trace()
        tname = threading.currentThread().getName()
        logging.info('Start method is invoked from thread {}'.format(tname))
        lib.start(self._ha_ctx, self._c_str(rpc_endpoint), process.to_c(),
                  ha_service.to_c(), rm_service.to_c())

    def _c_str(self, str_val: str) -> c.c_char_p:
        if not str_val:
            return None
        byte_str = str_val.encode('utf-8')
        return c.c_char_p(byte_str)

    def test(self):
        tname = threading.currentThread().getName()
        logging.info('Test method is invoked from thread {}'.format(tname))
        _test(self._ha_ctx)
        # TODO call m0d from here

    def test_cb(self, data):
        logging.debug("Sending the test message to the queue")
        # TODO the actual data must be put here
        self.queue.put(Message(data))
        logging.debug("The locality thread is free now")

    def _entrypoint_request_cb(self, req_id, remote_rpc_endpoint, process_fid,
                               git_rev, pid, is_first_request):
        import pudb
        pudb.set_trace()
        raise NotImplementedError("TODO")
