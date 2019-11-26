import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, NamedTuple, Tuple

from hax.types import Fid
from hax.util import ConsulUtil, create_process_fid

HAState = NamedTuple('HAState', [('fid', Fid), ('status', str)])


class KVHandler(BaseHTTPRequestHandler):
    def __init__(self, req, client_addr, server):
        super().__init__(req, client_addr, server)
        self.server = server

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        self._set_headers()
        result = json.dumps({'message': 'I am alive'})
        self.wfile.write(result.encode())

    def do_HEAD(self):
        self._set_headers()

    def do_POST(self):
        self._set_headers()
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        logging.debug('POST request received: %s', post_data)

        ha_states = self.to_ha_states(KVHandler.parse_json(post_data))
        logging.info('HA states: %s', ha_states)
        self.server.halink.broadcast_ha_states(ha_states)
        logging.debug('POST request processed')

    @staticmethod
    def parse_json(raw_data: bytes) -> Any:
        try:
            return json.loads(raw_data.decode('utf-8'))
        except json.JSONDecodeError:
            logging.warning('Invalid JSON object received')

    @staticmethod
    def to_ha_states(data: Any) -> List[HAState]:
        """Converts a dictionary, obtained from JSON data, into a list of
        HA states.

        Format of an HA state: HAState(fid= <service fid>, status= <state>),
        where <state> is either 'online' or 'offline'.
        """
        if not data:
            return []

        def get_status(checks: List[Dict[str, Any]]) -> str:
            ok = all(x.get('Status') == 'passing' for x in checks)
            return 'online' if ok else 'offline'

        return [
            HAState(fid=create_process_fid(int(t['Service']['ID'])),
                    status=get_status(t['Checks'])) for t in data
        ]


def run_server(thread_to_wait=None,
               server_class=HTTPServer,
               port=8080,
               halink=None):
    port = 8080
    addr = ConsulUtil().get_hax_ip_address()
    server_address: Tuple[str, int] = (addr, port)
    httpd = server_class(server_address, KVHandler)
    httpd.halink = halink

    logging.info(f'Starting HTTP server at {addr}:{port} ...')
    try:
        httpd.serve_forever()
    finally:
        if thread_to_wait is not None:
            thread_to_wait.is_stopped = True
            thread_to_wait.join()
        logging.info('The http server has stopped')
