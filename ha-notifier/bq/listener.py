#!/usr/bin/env python

import sys
import os
import json
import base64
import logging


def filter_old_messages(msg_list):
    # XXX to be implemented later
    return msg_list


def extract_value(msg):
    assert isinstance(msg, dict)
    v = msg['Value']
    v = base64.b64decode(v)
    return v.decode('utf-8')


def get_messages(raw_input):
    msgs = json.loads(raw_input)
    if not msgs:
        msgs = []
    msgs = filter_old_messages(msgs)
    return list(map(extract_value, msgs))


def setup_logging():
    logging.basicConfig(level=logging.DEBUG, filename='listener.log')


def main():
    setup_logging()
    lines = []
    for line in sys.stdin:
        lines.append(line)
    raw_in = os.linesep.join(lines)
    logging.debug("Input: {}".format(raw_in))
    msgs = get_messages(raw_in)
    for m in msgs:
        print(m)


if __name__ == "__main__":
    main()
