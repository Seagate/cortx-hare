import consul as c
from hax.types import Fid

SERVICE_CONTAINER = 0x7300000000000001


class FidProvider(object):
    def get_hax_fid(self):
        client = c.Consul()
        services = client.agent.services()
        for k, v in services.items():
            if v.get('Service') == 'hax':
                return Fid.parse(k)
        raise RuntimeError('No hax service found in Consul')
