import json
import logging
from queue import Queue
from typing import Any, Callable, Dict, List, Optional, Tuple

from hax.message import BroadcastHAStates
from hax.motr.delivery import DeliveryHerald
from hax.queue.confobjutil import ConfObjUtil
from hax.types import (Fid, HaLinkMessagePromise, HAState, MessageId,
                       ServiceHealth)

LOG = logging.getLogger('hax')


class BQProcessor:
    """
    Broadcast Queue Processor.

    This is the place where a real processing logic should be located.
    """

    def __init__(self, queue: Queue, delivery_herald: DeliveryHerald):
        self.queue = queue
        self.confobjutil = ConfObjUtil()
        self.herald = delivery_herald

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
            'STOB_IOQ_ERROR': self.handle_ioq_stob_error,
        }
        if msg_type in handlers:
            handlers[msg_type](payload)
        elif msg_type == 'HA_NOTIFY':
            self.handle_ha_notify(payload)
        else:
            LOG.warn('Unsupported message type given: %s. Message skipped.',
                     msg_type)
            return

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
        self.queue.put(BroadcastHAStates(states=[hastate],
                                         is_broadcast_local=True,
                                         reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def handle_ioq_stob_error(self, payload: Dict[str, Any]) -> None:
        fid = Fid.parse(payload['conf_sdev'])
        if fid.is_null():
            LOG.debug('Fid is 0:0. Skipping the message.')
            return

        q: Queue = Queue(1)
        self.queue.put(
            BroadcastHAStates(
                states=[HAState(fid,
                                status=ServiceHealth.FAILED)],
                is_broadcast_local=True, reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def to_ha_state(self, objinfo: Dict[str, str]) -> Optional[HAState]:
        try:
            sdev_fid = self.confobjutil.drive_to_sdev_fid(
                objinfo['node'], objinfo['device'])
            state = ServiceHealth.OK if objinfo[
                'state'] == 'online' else ServiceHealth.FAILED
        except KeyError as error:
            LOG.error('Invalid json payload, no key (%s) present', error)
            return None
        return HAState(sdev_fid, status=state)

    def handle_ha_notify(self, payload: List[Dict[str, Any]]) -> None:
        hastates: List[HAState] = []
        for state in payload:
            hastatus = ServiceHealth.UNKNOWN
            if state['status'] == 'FAILED':
                hastatus = ServiceHealth.FAILED
            elif state['status'] == 'OK':
                hastatus = ServiceHealth.OK
            hastates.append(HAState(Fid.parse(state['fid']), hastatus))

        if hastates:
            q: Queue = Queue(1)
            self.queue.put(BroadcastHAStates(states=hastates,
                                             is_broadcast_local=True,
                                             reply_to=q))
            ids: List[MessageId] = q.get()
            self.herald.wait_for_any(HaLinkMessagePromise(ids))
