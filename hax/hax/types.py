

# Duplicates mero/fid/fid.h
# TODO implement more methods
class Fid(object):
    def __init__(self, container, key):
        self.container = container
        self.key = key


class Uint128(object):
    def __init__(self, hi, lo):
        self.hi = hi
        self.lo = lo
