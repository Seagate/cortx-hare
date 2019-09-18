import ctypes as c
import logging
import threading
from errno import EAGAIN

from hax.ffi import HaxFFI, make_array, make_c_str
from hax.message import EntrypointRequest, ProcessEvent
from hax.types import ConfHaProcess, Fid, FidStruct, HaNoteStruct
from hax.util import ConsulUtil


def log_exception(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logging.exception('**ERROR**')

    return wrapper


class HaLink:
    def __init__(self, node_uuid='', ffi=None, queue=None, rm_fid=None):
        self._ffi = ffi or HaxFFI()
        # [KN] Note that node_uuid is currently ignored by the corresponding
        # hax.c function
        self._ha_ctx = self._ffi.init_halink(self, make_c_str(node_uuid))
        self.queue = queue
        self.rm_fid = rm_fid

        if not self._ha_ctx:
            logging.error(
                'Cannot initialize ha_link. m0_halon_interface::init_halink' +
                ' returned 0')
            raise RuntimeError('Cannot initialize ha_link')

    def start(self, rpc_endpoint: str, process: Fid, ha_service: Fid,
              rm_service: Fid):
        logging.debug('Starting m0_halon_interface')
        result = self._ffi.start(self._ha_ctx, make_c_str(rpc_endpoint),
                                 process.to_c(), ha_service.to_c(),
                                 rm_service.to_c())
        if not result:
            logging.error('Cannot start ha_link. m0_halon_interface::start' +
                          ' returned 0')
            raise RuntimeError('Cannot start m0_halon_interface.' +
                               'Please check mero logs for more details.')

    @log_exception
    def _entrypoint_request_cb(self, reply_context, req_id,
                               remote_rpc_endpoint, process_fid, git_rev, pid,
                               is_first_request):
        logging.debug('Received entrypoint request from remote endpoint'
                      " '{}', process fid = {}".format(remote_rpc_endpoint,
                                                       str(process_fid)) +
                      ' The request will be processed in another thread.')
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

        logging.debug('Processing entrypoint request from remote endpoint'
                      " '{}', process fid {}".format(remote_rpc_endpoint,
                                                     str(process_fid)))
        sess = principal_rm = confds = None
        try:
            prov = ConsulUtil()
            sess = prov.get_leader_session()
            principal_rm = prov.get_session_node(sess)
            confds = prov.get_confd_list()
        except Exception:
            logging.exception('Failed to get the data from Consul.'
                              ' Replying with EAGAIN error code.')
            self._ffi.entrypoint_reply(reply_context, req_id.to_c(), EAGAIN, 0,
                                       make_array(FidStruct, []),
                                       make_array(c.c_char_p, []), 0,
                                       self.rm_fid.to_c(), None)
            logging.debug('Reply sent')
            return

        rc_quorum = int(len(confds) / 2 + 1)

        rm_eps = None
        for cnf in confds:
            if cnf.get('node') == principal_rm:
                rm_eps = cnf.get('address')
                break

        confd_fids = [x.get('fid').to_c() for x in confds]
        confd_eps = [make_c_str(x.get('address')) for x in confds]

        logging.debug('Passing the entrypoint reply to hax.c layer')
        self._ffi.entrypoint_reply(reply_context, req_id.to_c(), 0,
                                   len(confds),
                                   make_array(FidStruct, confd_fids),
                                   make_array(c.c_char_p,
                                              confd_eps), rc_quorum,
                                   self.rm_fid.to_c(), make_c_str(rm_eps))
        logging.debug('Entrypoint request has been replied to')

    def broadcast_ha_states(self, ha_states):
        logging.debug('Broadcasting HA states %s over ha_link', ha_states)

        def ha_obj_state(st):
            return HaNoteStruct.M0_NC_ONLINE if st['status'] == 'online' \
                else HaNoteStruct.M0_NC_FAILED

        notes = [
            HaNoteStruct(st['fid'].to_c(), ha_obj_state(st))
            for st in ha_states
        ]
        self._ffi.ha_broadcast(self._ha_ctx, make_array(HaNoteStruct, notes),
                               len(notes))

    def _process_event_cb(self, fid, chp_event, chp_type, chp_pid):
        logging.info('fid=%s, chp_event=%s', fid, chp_event)
        self.queue.put(
            ProcessEvent(
                ConfHaProcess(chp_event=chp_event,
                              chp_type=chp_type,
                              chp_pid=chp_pid,
                              fid=fid)))

    def close(self):
        logging.debug('Destroying ha_link')
        self._ffi.destroy(self._ha_ctx)
        self._ha_ctx = 0
        logging.debug('ha_link destroyed. Bye!')

    # TODO refactor: Separate the C calls from HaLink class,
    # so that hax.c functions can be invoked outside of HaLink instance.
    def adopt_mero_thread(self):
        logging.debug('Adopting mero thread')
        self._ffi.adopt_mero_thread()

    def shun_mero_thread(self):
        self._ffi.shun_mero_thread()
