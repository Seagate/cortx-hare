import ctypes as c


class FidStruct(c.Structure):
    _fields_ = [("f_container", c.c_uint64),
                ("f_key", c.c_uint64)]


class Uint128Struct(c.Structure):
    _fields_ = [("hi", c.c_uint64),
                ("lo", c.c_uint64)]


# Duplicates mero/fid/fid.h
# TODO implement more methods
class Fid(object):
    def __init__(self, container, key):
        self.container = container
        self.key = key

    def to_c(self):
        return FidStruct(self.container, self.key)


class Uint128(object):
    def __init__(self, hi, lo):
        self.hi = hi
        self.lo = lo

    def to_c(self):
        return Uint128Struct(self.hi, self.lo)
