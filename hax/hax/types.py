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


# Mostly duplicates mero/conf/ha.h:m0_conf_ha_process
class ConfHaProcess:
    def __init__(self, chp_event=0, chp_type=0, chp_pid=0, fid=None):
        self.chp_event = chp_event
        self.chp_type = chp_type
        self.chp_pid = chp_pid
        self.fid = fid


# Duplicates mero/fid/fid.h
class Fid:
    def __init__(self, container, key):
        self.container = int(container)
        self.key = int(key)

    @staticmethod
    def parse(val: str):
        cont, key = tuple(int(s, 16) for s in val.split(':', 1))
        return Fid(cont, key)

    def to_c(self):
        return FidStruct(self.container, self.key)

    def get_copy(self):
        return Fid(self.container, self.key)

    def __repr__(self):
        return f'{self.container:#x}:{self.key:#x}'

    def __eq__(self, other):
        return type(other) is Fid and \
            other.container == self.container and other.key == self.key


class Uint128:
    def __init__(self, hi, lo):
        self.hi = hi
        self.lo = lo

    def __repr__(self):
        return f'{self.hi:#x}:{self.lo:#x}'

    def to_c(self):
        return Uint128Struct(self.hi, self.lo)
