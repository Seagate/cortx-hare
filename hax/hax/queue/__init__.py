import logging
from typing import Any, List, Tuple


class BQProcessor:
    """
    This is the place where a real processing logic should be located.
    Currently it is effectively a no-op.
    """
    def process(self, messages: List[Tuple[int, Any]]) -> None:
        for i, msg in messages:
            logging.debug('Message #%s received: %s (type: %s)', i, msg,
                          type(msg).__name__)
