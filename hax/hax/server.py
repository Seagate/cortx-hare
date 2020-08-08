# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Tuple

from hax.types import HAState, StoppableThread
from hax.util import ConsulUtil, create_process_fid


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


def run_server(threads_to_wait: List[StoppableThread] = [],
               server_class=HTTPServer,
               port=8008,
               halink=None):
    addr = ConsulUtil().get_hax_ip_address()
    server_address: Tuple[str, int] = (addr, port)
    httpd = server_class(server_address, KVHandler)
    httpd.halink = halink

    logging.info(f'Starting HTTP server at {addr}:{port} ...')
    try:
        httpd.serve_forever()
    finally:
        for thread in threads_to_wait:
            thread.stop()
        for thread in threads_to_wait:
            thread.join()

        logging.info('The http server has stopped')
