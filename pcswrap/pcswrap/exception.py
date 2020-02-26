from dataclasses import dataclass


class PcsException(RuntimeError):
    pass


@dataclass(eq=False)
class PcsNoStatusException(PcsException):
    message: str


@dataclass(eq=False)
class CliException(PcsException):
    out: str
    err: str
    exit_code: int
