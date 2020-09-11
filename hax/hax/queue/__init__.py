import json
import logging
from queue import Queue
from typing import Any, Callable, Dict, List, Optional, Tuple

from hax.message import BroadcastHAStates
from hax.motr.delivery import DeliveryHerald
from hax.queue.confobjutil import ConfObjUtil
from hax.types import Fid, HaLinkMessagePromise, HAState, MessageId
from hax.util import create_drive_fid


class BQProcessor:
    """
    This is the place where a real processing logic should be located.
    Currently it is effectively a no-op.
    """
    def __init__(self, queue: Queue, delivery_herald: DeliveryHerald):
        self.queue = queue
        self.confobjutil = ConfObjUtil()
        self.herald = delivery_herald

    def process(self, message: Tuple[int, Any]) -> None:
        (i, msg) = message
        logging.debug('Message #%d received: %s (type: %s)', i, msg,
                      type(msg).__name__)
        try:
            self.payload_process(msg)
        except Exception:
            logging.exception(
                'Failed to process a message #%d.'
                ' The message is skipped.', i)
        logging.debug('Message #%d processed', i)

    def payload_process(self, msg: str) -> None:
        data = None
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            logging.error('Cannot parse payload, invalid json')
            return

        payload = data['payload']
        msg_type = data['message_type']

        handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {
            'M0_HA_MSG_NVEC': self.handle_device_state_set,
            'STOB_IOQ_ERROR': self.handle_ioq_stob_error,
        }
        if msg_type not in handlers:
            logging.warn(
                'Unsupported message type given: %s. Message skipped.',
                msg_type)
            return
        handlers[msg_type](payload)

    def handle_device_state_set(self, payload: Dict[str, Any]) -> None:
        # To add check for multiple object entries in a payload.
        # for objinfo in payload:
        hastate: Optional[HAState] = self.to_ha_state(payload)
        if not hastate:
            logging.debug('No ha states to broadcast.')
            return

        q: Queue = Queue(1)
        self.queue.put(BroadcastHAStates(states=[hastate], reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def handle_ioq_stob_error(self, payload: Dict[str, Any]) -> None:
        fid = Fid.parse(payload['conf_sdev'])
        if fid.is_null():
            logging.debug('Fid is 0:0. Skipping the message.')
            return

        q: Queue = Queue(1)
        self.queue.put(
            BroadcastHAStates(states=[HAState(fid, status='offline')],
                              reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def to_ha_state(self, objinfo: dict) -> Optional[HAState]:
        try:
            drive_id = self.confobjutil.obj_name_to_id(objinfo['obj_type'],
                                                       objinfo['obj_name'])
        except KeyError as error:
            logging.error('Invalid json payload, no key (%s) present', error)
            return None
        return HAState(fid=create_drive_fid(int(drive_id)),
                       status=objinfo['obj_state'])
