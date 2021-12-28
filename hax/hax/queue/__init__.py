import json
import logging
from queue import Queue
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast

from hax.message import BroadcastHAStates
from hax.motr.delivery import DeliveryHerald
from hax.motr.planner import WorkPlanner
from hax.queue.confobjutil import ConfObjUtil
from hax.types import (Fid, HaLinkMessagePromise, HAState, MessageId,
                       ServiceHealth)

LOG = logging.getLogger('hax')

PLD = Union[str, List[Any], Dict[str, Any]]


def as_dict(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(
            'Business logic error: payload was expected to be a dict, but '
            + type(payload).__name__ + ' was given')
    return cast(Dict[str, Any], payload)


class BQProcessor:
    """
    Broadcast Queue Processor.

    This is the place where a real processing logic should be located.
    """
    def __init__(self, planner: WorkPlanner, delivery_herald: DeliveryHerald,
                 conf_obj_util: ConfObjUtil):
        self.planner = planner
        self.confobjutil = conf_obj_util
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

        handlers: Dict[str, Callable[[PLD], None]] = {
            'M0_HA_MSG_NVEC': self.handle_device_state_set,
            'STOB_IOQ_ERROR': self.handle_ioq_stob_error,
            'MOTR_BCAST': self.handle_motr_bcast,
        }
        if msg_type not in handlers:
            LOG.warn('Unsupported message type given: %s. Message skipped.',
                     msg_type)
            return
        handlers[msg_type](payload)

    def handle_device_state_set(self, payload: PLD) -> None:
        # To add check for multiple object entries in a payload.
        # for objinfo in payload:
        payload = as_dict(payload)
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

    def handle_ioq_stob_error(self, payload: PLD) -> None:
        payload = as_dict(payload)
        fid = Fid.parse(payload['conf_sdev'])
        if fid.is_null():
            LOG.debug('Fid is 0:0. Skipping the message.')
            return

        q: Queue = Queue(1)
        self.planner.add_command(
            BroadcastHAStates(
                states=[HAState(fid,
                                status=ServiceHealth.FAILED)], reply_to=q))
        ids: List[MessageId] = q.get()
        self.herald.wait_for_any(HaLinkMessagePromise(ids))

    def handle_motr_bcast(self, payload: PLD) -> None:
        pass

    def to_ha_state(self, objinfo: Dict[str, Any]) -> Optional[HAState]:
        try:
            sdev_fid = self.confobjutil.drive_to_sdev_fid(
                objinfo['node'], objinfo['device'])
            state = ServiceHealth.OK if objinfo[
                'state'] == 'online' else ServiceHealth.FAILED
        except KeyError as error:
            LOG.error('Invalid json payload, no key (%s) present', error)
            return None
        return HAState(sdev_fid, status=state)
