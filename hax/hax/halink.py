import ctypes as c
import logging
import threading
import os
from errno import EAGAIN
from hax.types import Fid, FidStruct, Uint128Struct, HaNoteStruct
from hax.util import ConsulUtil
from hax.message import EntrypointRequest

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

        lib.m0_ha_notify.argtypes = [
            c.c_void_p,  # unsigned long long ctx
            c.POINTER(HaNoteStruct),  # struct m0_ha_note *notes
            c.c_uint32  # uint32_t nr_notes
        ]
        self.__ha_broadcast = lib.m0_ha_notify

        self._ha_ctx = self.__init_halink(self, self._c_str(node_uuid))
        self.queue = queue
        self.rm_fid = rm_fid

        lib.adopt_mero_thread.argtypes = []
        lib.adopt_mero_thread.restype = c.c_int
        self.__adopt_mero_thread = lib.adopt_mero_thread
        self.__shun_mero_thread = lib.m0_thread_shun

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

    @log_exception
    def _entrypoint_request_cb(self, reply_context, req_id,
                               remote_rpc_endpoint, process_fid, git_rev, pid,
                               is_first_request):
        logging.debug(
            ("Received entrypoint request from remote eps = '{}', " +
             "process_fid = {}." +
             " The request will be processed in another thread.").format(
                 remote_rpc_endpoint, str(process_fid)))
        self.queue.put(
            EntrypointRequest(reply_context=reply_context,
                              req_id=req_id,
                              remote_rpc_endpoint=remote_rpc_endpoint,
                              process_fid=process_fid,
                              git_rev=git_rev,
                              pid=pid,
                              is_first_request=is_first_request,
                              ha_link_instance=self))

    @log_exception
    def send_entrypoint_request_reply(self, message):
        assert isinstance(message, EntrypointRequest)
        reply_context = message.reply_context
        req_id = message.req_id
        remote_rpc_endpoint = message.remote_rpc_endpoint
        process_fid = message.process_fid

        logging.debug(
            "Started processing entrypoint request from remote eps = '{}', process_fid = {}"
            .format(remote_rpc_endpoint, str(process_fid)))

        make_array = self._make_arr
        sess = None
        principal_rm = None
        confds = None

        try:
            prov = ConsulUtil()
            sess = prov.get_leader_session()
            principal_rm = prov.get_session_node(sess)
            confds = prov.get_confd_list()
        except Exception:
            logging.exception("Failed to get the data from Consul. " +
                              "Replying with EAGAIN error code.")
            self.__entrypoint_reply(reply_context, req_id.to_c(), EAGAIN, 0,
                                    make_array(FidStruct, []),
                                    make_array(c.c_char_p, []), 0,
                                    self.rm_fid.to_c(), None)
            logging.debug("Reply sent")
            return

        rc_quorum = int(len(confds) / 2 + 1)

        rm_eps = None
        for cnf in confds:
            if cnf.get('node') == principal_rm:
                rm_eps = cnf.get('address')
                break
        confd_fids = list(map(lambda x: x.get('fid').to_c(), confds))
        confd_eps = list(map(lambda x: self._c_str(x.get('address')), confds))

        logging.debug("Pasing the entrypoint reply to hax.c layer")
        self.__entrypoint_reply(reply_context, req_id.to_c(), 0, len(confds),
                                make_array(FidStruct, confd_fids),
                                make_array(c.c_char_p, confd_eps), rc_quorum,
                                self.rm_fid.to_c(), self._c_str(rm_eps))
        logging.debug(
            "Entrypoint request replied, mero's locality thread is free now")

    def broadcast_service_states(self, service_states):
        logging.debug(
            "The following service states will be broadcasted via ha_link: {}".
            format(service_states))
        note_list = list(map(self._to_ha_note, service_states))
        self.__ha_broadcast(self._ha_ctx,
                            self._make_arr(HaNoteStruct, note_list),
                            len(note_list))

    def _to_ha_note(self, service_state):
        assert isinstance(service_state, dict)
        assert 'fid' in service_state
        assert 'status' in service_state
        fid = service_state.get('fid')
        status = service_state.get('status')

        int_status = HaNoteStruct.M0_NC_ONLINE
        if status != 0:
            int_status = HaNoteStruct.M0_NC_FAILED

        return HaNoteStruct(fid.to_c(), int_status)

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

    # TODO refactor: Separate the C calls from HaLink class, so that hax.c functions can be invoked outside of HaLink instance.
    def adopt_mero_thread(self):
        logging.debug("Adopting mero thread")
        self.__adopt_mero_thread()

    def shun_mero_thread(self):
        self.__shun_mero_thread()
