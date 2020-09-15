from hax.util import ConsulUtil


class ConfObjUtil:
    def __init__(self):
        self.consul = ConsulUtil()

    def drive_to_sdev_fid(self, node: str, drive: str):
        return self.consul.node_to_drive_fid(node, drive)
