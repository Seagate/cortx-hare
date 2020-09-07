import json
import logging
from queue import Queue
from typing import Any, List, Optional, Tuple

from hax.motr.delivery import DeliveryHerald
from hax.queue.confobjutil import ConfObjUtil
from hax.types import HaLinkMessagePromise, HAState, MessageId
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

    def process(self, messages: List[Tuple[int, Any]]) -> None:
        for i, msg in messages:
            logging.debug('Message #%s received: %s (type: %s)', i, msg,
                          type(msg).__name__)
            self.payload_process(msg)

    def payload_process(self, msg: str) -> None:
        #
        # XXX:
        # differing import temporarily due to following runtime error suspected
        # due to
        # import dependency,
        # from hax.message import EntrypointRequest, HaNvecGetEvent,
        # ProcessEvent
        # ImportError: cannot import name 'EntrypointRequest'
        #
        from hax.message import BroadcastHAStates
        hastates = []
        try:
            msg_load = json.loads(msg)
            payload = json.loads(msg_load['payload'])
        except json.JSONDecodeError:
            logging.error('Cannot parse payload, invalid json')
            return
        # To add check for multiple object entries in a payload.
        # for objinfo in payload:
        hastate: Optional[HAState] = self.to_ha_state(payload)
        if hastate:
            hastates.append(hastate)
        if not hastates:
            logging.debug('No ha states to broadcast')
            return

        q: Queue = Queue(1)
        self.queue.put(BroadcastHAStates(states=hastates, reply_to=q))
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
