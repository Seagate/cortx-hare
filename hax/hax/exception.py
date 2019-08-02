class ConsulException(RuntimeError):
    pass


class HAConsistencyException(ConsulException):
    pass
