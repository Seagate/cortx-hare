#!/usr/bin/env python

import sys
import os
import json
import base64
import logging
import subprocess


def filter_old_messages(msg_list):
    # XXX to be implemented later
    return msg_list

def get_mero_path():
    # TODO move this to a config?
    return os.path.expanduser('~') + '/projects/mero/'


def extract_value(msg):
    assert isinstance(msg, dict)
    v = msg['Value']
    v = base64.b64decode(v)
    logging.debug("Decoded: {}".format(v))
    return v.decode('utf-8')


def get_messages(raw_input):
    msgs = json.loads(raw_input)
    if not msgs:
        msgs = []
    msgs = filter_old_messages(msgs)
    return list(map(extract_value, msgs))


def setup_logging():
    logging.basicConfig(level=logging.DEBUG, filename='listener.log')


def forward(message):
    path = get_mero_path() + 'utils'
    to_xcode = subprocess.Popen(['{}/m0hagen'.format(path)],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env={},
                                encoding='utf8')

    to_m0d = subprocess.Popen(['{}/m0ham'.format(path)],
                              stdin=to_xcode.stdout,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              env={},
                              encoding='utf8')

    logging.debug("Forwarding the following message as an input to m0hagen: {}".format(message))
    out, err = to_xcode.communicate(input=message)
    ham_out, ham_err = to_m0d.communicate()
    logging.debug("m0hagen exited with code {}".format(to_xcode.returncode))
    logging.debug("m0ham exited with code {}".format(to_m0d.returncode))
    logging.debug("-------------------------")
    logging.debug("m0hagen Output: {}".format(out))
    logging.debug("m0hagen stderr: {}".format(err))
    logging.debug("m0ham Output: {}".format(ham_out))
    logging.debug("m0ham stderr: {}".format(ham_err))
    logging.debug("=========================")


def main():
    setup_logging()
    lines = []
    for line in sys.stdin:
        lines.append(line)
    raw_in = os.linesep.join(lines)
    logging.debug("Input: {}".format(raw_in))
    msgs = get_messages(raw_in)
    for m in msgs:
        forward(m)


if __name__ == "__main__":
    main()
