from dataclasses import dataclass


class PcsException(RuntimeError):
    pass


class TimeoutException(PcsException):
    pass


@dataclass(eq=False)
class PcsNoStatusException(PcsException):
    message: str


@dataclass(eq=False)
class MaintenanceFailed(PcsException):
    pass


@dataclass(eq=False)
class CliException(PcsException):
    out: str
    err: str
    exit_code: int
