import json
import logging
from queue import Queue
from typing import Any, Callable, Dict, List, Optional, Tuple

from hax.message import (BaseMessage, BroadcastHAStates, ProcessHaEvent,
                         SnsDiskAttach, SnsDiskDetach, SnsRebalancePause,
                         SnsRebalanceResume, SnsRebalanceStart,
                         SnsRebalanceStop, SnsRepairPause,
                         SnsRepairResume, SnsRepairStart, SnsRepairStop)
from hax.motr import Motr
from hax.motr.delivery import DeliveryHerald
from hax.motr.planner import WorkPlanner
from hax.queue.confobjutil import ConfObjUtil
from hax.types import (Fid, HaLinkMessagePromise, HAState, MessageId,
                       ObjHealth, m0HaProcessEvent, m0HaProcessType)

LOG = logging.getLogger('hax')


class BQProcessor:

    """
    Broadcast Queue Processor.

    This is the place where a real processing logic should be located.
    """
    def __init__(self, planner: WorkPlanner, delivery_herald: DeliveryHerald,
                 motr: Motr, conf_obj_util: ConfObjUtil):
        self.planner = planner
        self.confobjutil = conf_obj_util
        self.herald = delivery_herald
        self.motr = motr

    def process(self, message: Tuple[int, Any]) -> None:
        (i, msg) = message
        LOG.debug('Message #%d received: %s (type: %s)', i, msg,
                  type(msg).__name__)
        try:
            self.payload_process(msg)
        except Exception:
            LOG.exception(
                'Failed to process a message #%d.'
                ' The message is skipped.', i)
        LOG.debug('Message #%d processed', i)

    def payload_process(self, msg: str) -> None:
        data = None
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            LOG.error('Cannot parse payload, invalid json')
            return

        payload = data['payload']
        msg_type = data['message_type']

        handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {
            'M0_HA_MSG_NVEC': self.handle_device_state_set,
            'SNS_OP': self.handle_sns_op,
            'STOB_IOQ_ERROR': self.handle_ioq_stob_error,
            'PROCESS-STATE-UPDATE': self.handle_process_state_update
        }
        if msg_type not in handlers:
            LOG.warn('Unsupported message type given: %s. Message skipped.',
                     msg_type)
            return
        handlers[msg_type](payload)

    def handle_process_state_update(self, payload: Dict[str, Any]) -> None:
        def _get_ha_state() -> Optional[HAState]:
            try:
                fid = Fid.parse(payload['fid'])
                state_val = getattr(m0HaProcessEvent, payload['state'])
                state = state_val.event_to_svchealth()
            except (KeyError, AttributeError) as error:
                LOG.error('Invalid json payload, no key (%s) present', error)
                return None
            return HAState(fid, status=state)

        hastate: Optional[HAState] = _get_ha_state()
        LOG.debug('ProcessStateUpdate process fid: %s state: %s, type: %s',
                  payload['fid'], payload['state'], payload['type'])
        self.planner.add_command(
            ProcessHaEvent(fid=Fid.parse(payload['fid']),
                           proc_type=getattr(m0HaProcessType,
                                             payload['type']),
                           states=[hastate]))

    def handle_device_state_set(self, payload: Dict[str, Any]) -> None:
        # To add check for multiple object entries in a payload.
        # for objinfo in payload:
        hastate: Optional[HAState] = self.to_ha_state(payload)
        if not hastate:
            LOG.debug('No ha states to broadcast.')
            return

        q: Queue = Queue(1)
        LOG.debug('HA broadcast, node: %s device: %s state: %s',
                  payload['node'], payload['device'], payload['state'])
        self.planner.add_command(
            BroadcastHAStates(states=[hastate], reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def handle_sns_op(self, payload: Dict[str, Any]) -> None:
        op_name = payload['op_name']

        def create_handler(
            a_type: Callable[[Fid], BaseMessage]
        ) -> Callable[[Dict[str, Any]], BaseMessage]:
            def fn(data: Dict[str, Any]):
                fid = Fid.parse(data['fid'])
                return a_type(fid)
            return fn

        msg_factory = {
            'rebalance-start': create_handler(SnsRebalanceStart),
            'rebalance-stop': create_handler(SnsRebalanceStop),
            'rebalance-pause': create_handler(SnsRebalancePause),
            'rebalance-resume': create_handler(SnsRebalanceResume),
            'repair-start': create_handler(SnsRepairStart),
            'repair-stop': create_handler(SnsRepairStop),
            'repair-pause': create_handler(SnsRepairPause),
            'repair-resume': create_handler(SnsRepairResume),
            'disk-attach': create_handler(SnsDiskAttach),
            'disk-detach': create_handler(SnsDiskDetach),
        }

        LOG.debug(f'process_sns_operation: {op_name}')
        if op_name not in msg_factory:
            LOG.error('Invalid sns operation, (%s) ', op_name)
        message = msg_factory[op_name](payload)
        self.planner.add_command(message)

    def handle_ioq_stob_error(self, payload: Dict[str, Any]) -> None:
        fid = Fid.parse(payload['conf_sdev'])
        if fid.is_null():
            LOG.debug('Fid is 0:0. Skipping the message.')
            return

        q: Queue = Queue(1)
        self.planner.add_command(
            BroadcastHAStates(
                states=[HAState(fid,
                                status=ObjHealth.FAILED)], reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def to_ha_state(self, objinfo: Dict[str, str]) -> Optional[HAState]:
        hastate_to_objstate = {
            'online': ObjHealth.OK,
            'failed': ObjHealth.FAILED,
            'offline': ObjHealth.OFFLINE,
            'repair': ObjHealth.REPAIR,
            'repaired': ObjHealth.REPAIRED,
            'rebalance': ObjHealth.REBALANCE
        }
        try:
            sdev_fid = self.confobjutil.drive_to_sdev_fid(
                objinfo['node'], objinfo['device'])
            state = hastate_to_objstate[objinfo['state']]
        except KeyError as error:
            LOG.error('Invalid json payload, no key (%s) present', error)
            return None
        return HAState(sdev_fid, status=state)
