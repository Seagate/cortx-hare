class BaseMessage(object):
    pass


class Message(BaseMessage):
    def __init__(self, s):
        self.s = s


class EntrypointRequest(BaseMessage):
    def __init__(self,
                 reply_context=None,
                 req_id=None,
                 remote_rpc_endpoint=None,
                 process_fid=None,
                 git_rev=None,
                 pid=None,
                 is_first_request=None,
                 ha_link_instance=None):
        self.reply_context = reply_context
        self.req_id = req_id
        self.remote_rpc_endpoint = remote_rpc_endpoint
        self.process_fid = process_fid
        self.git_rev = git_rev
        self.pid = pid
        self.is_first_request = is_first_request
        self.ha_link_instance = ha_link_instance


class Die(BaseMessage):
    pass
