from hax.util import ConsulUtil


class ConfObjUtil:
    def __init__(self):
        self.consul = ConsulUtil()

    def obj_name_to_id(self, objtype: str, objname: str) -> str:
        # This depends on consul kv schema for storing drive configuration.
        # Presently returning a random value, must be replaced with a proper
        # function per object type.
        return '16'
