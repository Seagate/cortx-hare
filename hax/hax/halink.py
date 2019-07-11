import ctypes

lib = ctypes.cdll.LoadLibrary('./hax.so')
lib.init_halink.argtypes = [ctypes.py_object]


class HaLink(object):
    def __init__(self, node_uuid=""):
        self._ha_ctx = lib.init_halink(self)
        if not self._ha_ctx:
            raise RuntimeError("Could not initialize ha_link")

    def _entrypoint_request_cb(self,
                               req_id,
                               remote_rpc_endpoint,
                               process_fid,
                               git_rev,
                               pid,
                               is_first_request):
        raise NotImplementedError("TODO")
