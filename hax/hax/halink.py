import ctypes
import logging

lib = ctypes.cdll.LoadLibrary('/home/720599/projects/hare/hax/hax.so')

prototype = ctypes.PYFUNCTYPE(ctypes.c_ulonglong, ctypes.py_object)
prot2 = ctypes.PYFUNCTYPE(None, ctypes.c_void_p)

_init_halink = prototype(('init_halink', lib))
_test = prot2(('test', lib))
lib.init_halink.argtypes = [ctypes.py_object, ctypes.c_char_p]
lib.init_halink.restype = ctypes.c_void_p

lib.test.argtypes = [ctypes.c_ulonglong]


class HaLink(object):
    def __init__(self, node_uuid=""):
        byte_str = node_uuid.encode('utf-8')
        self._ha_ctx = lib.init_halink(self, ctypes.c_char_p(byte_str))
        if not self._ha_ctx:
            raise RuntimeError("Could not initialize ha_link")
        

    def start(self):
        pass

    def test(self):
        _test(self._ha_ctx)

    def test_cb(self):
        import pudb; pudb.set_trace()

    def _entrypoint_request_cb(self,
                               req_id,
                               remote_rpc_endpoint,
                               process_fid,
                               git_rev,
                               pid,
                               is_first_request):
        import pudb; pudb.set_trace()
        raise NotImplementedError("TODO")


