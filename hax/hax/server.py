from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import json


class KVHandler(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        self._set_headers()
        s = json.dumps({'message': 'I am alive'})
        self.wfile.write(s.encode('utf-8'))

    def do_HEAD(self):
        self._set_headers()

    def do_POST(self):
        self._set_headers()
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        logging.info("A new request has been received: {}".format(post_data))


def run_server(server_class=HTTPServer, port=8080):
    port = 8080
    server_address = ('', port)
    httpd = server_class(server_address, KVHandler)

    logging.info('Starting http server...')
    httpd.serve_forever()
