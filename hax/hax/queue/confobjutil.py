from typing import Optional

from hax.configmanager import ConfigManager, ConsulConfigManager


# TODO [KN] Do we realy need this class?
# FIXME remove me
class ConfObjUtil:
    def __init__(self, consul_util: Optional[ConfigManager]):
        self.consul = consul_util or ConsulConfigManager()

    def drive_to_sdev_fid(self, node: str, drive: str):
        return self.consul.node_to_drive_fid(node, drive)
