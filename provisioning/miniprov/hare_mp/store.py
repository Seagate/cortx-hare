from typing import Any

from cortx.utils.conf_store import ConfStore


def as_is(v: str) -> str:
    """
    Does no transformation, keeps the input string as is.
    """
    return v


class ValueProvider:
    def get(self, key: str) -> Any:
        return self._raw_get(key)

    def _raw_get(self, key: str) -> str:
        raise NotImplementedError()


class ConfStoreProvider(ValueProvider):
    def __init__(self, url: str):
        self.url = url
        conf = ConfStore()
        conf.load('hare', url)
        self.conf = conf

    def _raw_get(self, key: str) -> str:
        return self.conf.get('hare', key)
