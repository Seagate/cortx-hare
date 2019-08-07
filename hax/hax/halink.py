import ctypes as c
import logging
import threading
from errno import EAGAIN
from hax.types import Fid, FidStruct, HaNoteStruct
from hax.util import ConsulUtil
from hax.message import EntrypointRequest
from hax.ffi import HaxFFI, make_array, make_c_str


def log_exception(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logging.exception("error")

    return wrapper


class HaLink(object):
    def __init__(self, node_uuid="", ffi=None, queue=None, rm_fid=None):
        self._ffi = ffi or HaxFFI()
        self._ha_ctx = self._ffi.init_halink(self, make_c_str(node_uuid))
        self.queue = queue
        self.rm_fid = rm_fid

        if not self._ha_ctx:
            raise RuntimeError("Could not initialize ha_link")

    def start(self, rpc_endpoint: str, process: Fid, ha_service: Fid,
              rm_service: Fid):
        tname = threading.currentThread().getName()
        logging.info('Start method is invoked from thread {}'.format(tname))
        self._ffi.start(self._ha_ctx, make_c_str(rpc_endpoint),
                        process.to_c(), ha_service.to_c(), rm_service.to_c())

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
            ("Started processing entrypoint request from remote eps = '{}'," +
             " process_fid = {}").format(remote_rpc_endpoint,
                                         str(process_fid)))

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
            self._ffi.entrypoint_reply(reply_context, req_id.to_c(), EAGAIN, 0,
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
        confd_eps = list(map(lambda x: make_c_str(x.get('address')), confds))

        logging.debug("Passing the entrypoint reply to hax.c layer")
        self._ffi.entrypoint_reply(reply_context, req_id.to_c(), 0,
                                   len(confds),
                                   make_array(FidStruct, confd_fids),
                                   make_array(c.c_char_p,
                                              confd_eps), rc_quorum,
                                   self.rm_fid.to_c(), make_c_str(rm_eps))
        logging.debug(
            "Entrypoint request is replied to")

    def broadcast_service_states(self, service_states):
        logging.debug(
            "The following service states will be broadcasted via ha_link: {}".
            format(service_states))
        note_list = list(map(self._to_ha_note, service_states))
        self._ffi.ha_broadcast(self._ha_ctx,
                               make_array(HaNoteStruct, note_list),
                               len(note_list))

    def _to_ha_note(self, service_state):
        assert isinstance(service_state, dict)
        assert 'fid' in service_state
        assert 'status' in service_state
        fid = service_state.get('fid')
        status = service_state.get('status')

        int_status = HaNoteStruct.M0_NC_ONLINE
        if status != 'online':
            int_status = HaNoteStruct.M0_NC_FAILED

        return HaNoteStruct(fid.to_c(), int_status)

    def close(self):
        logging.debug("Destructing ha_link")
        self._ffi.destroy(self._ha_ctx)
        self._ha_ctx = 0
        logging.debug("ha_link destroyed. Bye!")

    # TODO refactor: Separate the C calls from HaLink class, so that hax.c functions can be invoked outside of HaLink instance.
    def adopt_mero_thread(self):
        logging.debug("Adopting mero thread")
        self._ffi.adopt_mero_thread()

    def shun_mero_thread(self):
        self._ffi.shun_mero_thread()
