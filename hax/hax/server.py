from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import json
import consul
from queue import Queue


class Message(object):
    pass


class StrMessage(Message):
    def __init__(self, s):
        self.s = s


class Die(Message):
    pass


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
        s = json.dumps({'message': 'I am alive'})
        self.wfile.write(s.encode('utf-8'))

    def do_HEAD(self):
        self._set_headers()

    def do_POST(self):
        queue = self.server.reply_queue
        self._set_headers()
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        logging.info("A new request has been received: {}".format(post_data))
        queue.put(StrMessage(post_data))
        logging.debug(
            "The message is put to the queue, the server thread is free again")


def run_server(queue, thread_to_wait=None, server_class=HTTPServer, port=8080):
    port = 8080
    server_address = ('', port)
    httpd = server_class(server_address, KVHandler)
    httpd.reply_queue = queue

    logging.info('Starting http server...')
    try:
        httpd.serve_forever()
    finally:
        queue.put(Die())
        if thread_to_wait is not None:
            thread_to_wait.join()
        logging.info('The http server has stopped')


def kv_publisher_thread(q: Queue):
    logging.info('Publisher thread has started')
    try:
        # client = consul.Consul()
        while True:
            logging.info('Waiting')
            item = q.get()
            # import pudb; pudb.set_trace()
            logging.info('Got something from the queue')
            if isinstance(item, Die):
                logging.info('Got posioned pill, exiting')
                break

            logging.debug('Sending message to Consul: {}'.format(item.s))
            # TODO what and where do we actually need to persist to KV?
            # client.kv.put('bq', item)
    finally:
        logging.info('Publisher thread has exited')
