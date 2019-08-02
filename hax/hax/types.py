import ctypes as c
import logging


class FidStruct(c.Structure):
    _fields_ = [("f_container", c.c_uint64), ("f_key", c.c_uint64)]


class Uint128Struct(c.Structure):
    _fields_ = [("hi", c.c_uint64), ("lo", c.c_uint64)]


class HaNoteStruct(c.Structure):
    # Constants for no_state field values as they are described in ha/note.h

    # /** Object state is unknown. */
    M0_NC_UNKNOWN = 0
    # /** Object can be used normally. */
    M0_NC_ONLINE = 1
    # /**
    # * Object has experienced a permanent failure and cannot be
    # * recovered.
    # */
    M0_NC_FAILED = 2
    # /**
    # * Object is experiencing a temporary failure. Halon will notify Mero
    # * when the object is available for use again.
    # */
    M0_NC_TRANSIENT = 3
    # /**
    # * This state is only applicable to the pool objects. In this state,
    # * the pool is undergoing repair, i.e., the process of reconstructing
    # * data lost due to a failure and storing them in spare space.
    # */
    M0_NC_REPAIR = 4
    # /**
    # * This state is only applicable to the pool objects. In this state,
    # * the pool device has completed sns repair. Its data is re-constructed
    # * on its corresponding spare space.
    # */
    M0_NC_REPAIRED = 5
    # /**
    # * This state is only applicable to the pool objects. Rebalance process
    # * is complementary to repair: previously reconstructed data is being
    # * copied from spare space to the replacement storage.
    # */
    M0_NC_REBALANCE = 6

    M0_NC_NR = 7

    _fields_ = [("no_id", FidStruct), ("no_state", c.c_uint32)]


# Duplicates mero/fid/fid.h
class Fid(object):
    def __init__(self, container, key):
        self.container = container
        self.key = key

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

    def __repr__(self):
        return '{}:{}'.format(hex(self.hi), hex(self.lo))

    def to_c(self):
        return Uint128Struct(self.hi, self.lo)
