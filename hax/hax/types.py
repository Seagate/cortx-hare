import ctypes as c
import logging


class FidStruct(c.Structure):
    _fields_ = [("f_container", c.c_uint64), ("f_key", c.c_uint64)]


class Uint128Struct(c.Structure):
    _fields_ = [("hi", c.c_uint64), ("lo", c.c_uint64)]


# Duplicates mero/fid/fid.h
# TODO implement more methods
class Fid(object):
    def __init__(self, container, key):
        self.container = container
        self.key = key
        logging.debug("Fid created: {}".format(str(self)))

    @staticmethod
    def parse(val: str):
        a, b = tuple(map(lambda x: int(x, 16), val.split(':')))
        return Fid(a, b)

    def to_c(self):
        return FidStruct(self.container, self.key)

    def get_copy(self):
        return Fid(self.container, self.key)

    def __repr__(self):
        return '{}:{}'.format(hex(self.container), hex(self.key))

    def __eq__(self, other):
        if not isinstance(other, Fid):
            return False
        return other.container == self.container and other.key == self.key


class Uint128(object):
    def __init__(self, hi, lo):
        self.hi = hi
        self.lo = lo
        logging.debug("Unit128 created: {}".format(str(self)))

    def __repr__(self):
        return '{}:{}'.format(hex(self.hi), hex(self.lo))

    def to_c(self):
        return Uint128Struct(self.hi, self.lo)
