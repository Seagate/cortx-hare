import ctypes as c
import logging
from errno import EAGAIN
from typing import Any, List

from hax.ffi import HaxFFI, make_array, make_c_str
from hax.message import EntrypointRequest, HaNvecGetEvent, ProcessEvent
from hax.types import (ConfHaProcess, Fid, FidStruct, FsStats, HaNote,
                       HaNoteStruct, HAState, ObjT)
from hax.util import ConsulUtil


def log_exception(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logging.exception('**ERROR**')

    return wrapper


class HaLink:
    def __init__(self, ffi: HaxFFI, queue, rm_fid: Fid, node_uuid: str = ''):
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
        self._process_fid = process
        result = self._ffi.start(self._ha_ctx, make_c_str(rpc_endpoint),
                                 process.to_c(), ha_service.to_c(),
                                 rm_service.to_c())
        if result:
            logging.error(
                'Cannot start ha_link. m0_halon_interface::start' +
                ' returned non-zero code (%s)', result)
            raise RuntimeError('Cannot start m0_halon_interface.' +
                               'Please check Mero logs for more details.')

    def start_rconfc(self) -> int:
        logging.debug('Starting rconfc')
        result: int = self._ffi.start_rconfc(self._ha_ctx,
                                             self._process_fid.to_c())
        if result:
            raise RuntimeError('Cannot start rconfc.' +
                               'Please check Mero logs for more details.')
        logging.debug('rconfc started')
        return result

    @log_exception
    def _entrypoint_request_cb(self, reply_context: Any, req_id: Any,
                               remote_rpc_endpoint: str, process_fid: Fid,
                               git_rev: str, pid: int, is_first_request: bool):
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

    def send_entrypoint_request_reply(self, message: EntrypointRequest):
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
            sess = prov.get_leader_session_no_wait()
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
        for svc in confds:
            if svc.node == principal_rm:
                rm_eps = svc.address
                break
        if not rm_eps:
            raise RuntimeError('No RM node found in Consul')

        confd_fids = [x.fid.to_c() for x in confds]
        confd_eps = [make_c_str(x.address) for x in confds]

        logging.debug('Passing the entrypoint reply to hax.c layer')
        self._ffi.entrypoint_reply(reply_context, req_id.to_c(), 0,
                                   len(confds),
                                   make_array(FidStruct, confd_fids),
                                   make_array(c.c_char_p,
                                              confd_eps), rc_quorum,
                                   self.rm_fid.to_c(), make_c_str(rm_eps))
        logging.debug('Entrypoint request has been replied to')

    def broadcast_ha_states(self, ha_states: List[HAState]):
        logging.debug('Broadcasting HA states %s over ha_link', ha_states)
        cns = ConsulUtil()

        def ha_obj_state(st):
            return HaNoteStruct.M0_NC_ONLINE if st.status == 'online' \
                else HaNoteStruct.M0_NC_FAILED

        notes = []
        for st in ha_states:
            note = HaNoteStruct(st.fid.to_c(), ha_obj_state(st))
            notes.append(note)
            notes += self._generate_sub_services(note, cns)

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

    @log_exception
    def ha_nvec_get(self, hax_msg: int, nvec: List[HaNote]) -> None:
        logging.debug('Got ha nvec of length %s from Mero land', len(nvec))
        self.queue.put(HaNvecGetEvent(hax_msg, nvec, self))

    @log_exception
    def ha_nvec_get_reply(self, event: HaNvecGetEvent) -> None:
        logging.debug(
            'Preparing the reply for HaNvecGetEvent (nvec size = %s)',
            len(event.nvec))
        cutil = ConsulUtil()
        notes: List[HaNoteStruct] = []
        for n in event.nvec:
            n.note.no_state = HaNoteStruct.M0_NC_ONLINE
            if n.obj_t in (ObjT.PROCESS.name, ObjT.SERVICE.name) and \
               cutil.get_conf_obj_status(ObjT[n.obj_t],
                                         n.note.no_id.f_key) != 'passing':
                n.note.no_state = HaNoteStruct.M0_NC_FAILED
            notes.append(n.note)

        logging.debug('Replying ha nvec of length ' + str(len(event.nvec)))
        self._ffi.ha_nvec_reply(event.hax_msg, make_array(HaNoteStruct, notes),
                                len(notes))

    def _generate_sub_services(self, note: HaNoteStruct,
                               cns: ConsulUtil) -> List[HaNoteStruct]:
        new_state = note.no_state
        fid = Fid.from_struct(note.no_id)
        service_list = cns.get_services_by_parent_process(fid)
        logging.debug('Process fid=%s encloses %s services as follows: %s',
                      fid, len(service_list), service_list)
        return [
            HaNoteStruct(no_id=x.fid.to_c(), no_state=new_state)
            for x in service_list
        ]

    def close(self):
        logging.debug('Destroying ha_link')
        self._ffi.destroy(self._ha_ctx)
        self._ha_ctx = 0
        logging.debug('ha_link destroyed. Bye!')

    def adopt_mero_thread(self):
        logging.debug('Adopting Mero thread')
        self._ffi.adopt_mero_thread()

    def shun_mero_thread(self):
        self._ffi.shun_mero_thread()

    def get_filesystem_stats(self) -> FsStats:
        stats: FsStats = self._ffi.filesystem_stats_fetch(self._ha_ctx)
        return stats
