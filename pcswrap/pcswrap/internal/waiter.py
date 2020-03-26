import logging
from pcswrap.exception import TimeoutException
from time import sleep


class Waiter:
    def __init__(self,
                 title: str = '',
                 provider_fn=None,
                 predicate=None,
                 pause_seconds=2,
                 timeout_seconds=120):
        assert provider_fn
        assert predicate
        self.provider_fn = provider_fn
        self.predicate = predicate
        self.pause_seconds = pause_seconds
        self.timeout_seconds = timeout_seconds
        self.title = title

    def wait(self):
        time_left = self.timeout_seconds
        msg = self.title
        logging.debug(
            f'Waiting for condition "{msg}", timeout = {time_left} sec')
        while True:
            data = self.provider_fn()
            ok = self.predicate(data)
            logging.debug(f'{msg}? - {ok}')
            if ok:
                logging.debug(f'Condition "{msg}" is met, exiting')
                return
            time_left = time_left - self.pause_seconds
            if time_left <= 0:
                logging.debug(f'Condition "{msg}" is not met,'
                              ' exiting by timeout')
                raise TimeoutException()
            sleep(self.pause_seconds)
