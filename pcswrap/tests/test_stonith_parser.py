# flake8: noqa: E401
import sys
sys.path.insert(0, '..')
from unittest.mock import MagicMock, call
from pcswrap.types import StonithResource
from pcswrap.internal.connector import StonithParser
from typing import Tuple
import unittest


class StonithParserTest(unittest.TestCase):
    def test_parser_works(self):
        p = StonithParser()
        raw_text = '''
 Resource: stonith-c1 (class=stonith type=fence_ipmilan)
  Attributes: delay=5 ipaddr=10.230.244.112 login=ADMIN passwd=adminBMC! pcmk_host_check=static-list pcmk_host_list=srvnode-1 power_timeout=40
  Operations: monitor interval=10s (stonith-c1-monitor-interval-10s)
'''        
        result = p.parse(raw_text)
        self.assertIsNotNone(result)
        self.assertEqual('stonith', result.klass)
        self.assertEqual('fence_ipmilan', result.typename)
        self.assertEqual('10.230.244.112', result.ipaddr)
        self.assertEqual('ADMIN', result.login)
        self.assertEqual('adminBMC!', result.passwd)

    def test_only_ipmi_supported(self):
        p = StonithParser()
        raw_text = '''
 Resource: stonith-c1 (class=stonith type=fence_dummy)
  Attributes: delay=5 ipaddr=10.230.244.112 login=ADMIN passwd=adminBMC! pcmk_host_check=static-list pcmk_host_list=srvnode-1 power_timeout=40
  Operations: monitor interval=10s (stonith-c1-monitor-interval-10s)
'''        
        with self.assertRaises(AssertionError):
            p.parse(raw_text)

    def test_emptyilnes_ignored(self):
        p = StonithParser()
        raw_text = '''

 Resource: stonith-c1 (class=stonith type=fence_ipmilan)

  Attributes: delay=5 ipaddr=10.230.244.112 login=ADMIN passwd=adminBMC! pcmk_host_check=static-list pcmk_host_list=test-2 power_timeout=40
  Operations: monitor interval=10s (stonith-c1-monitor-interval-10s)
'''        
        result = p.parse(raw_text)
        self.assertIsNotNone(result)
        self.assertEqual('stonith', result.klass)
        self.assertEqual('fence_ipmilan', result.typename)
        self.assertEqual('10.230.244.112', result.ipaddr)
        self.assertEqual('ADMIN', result.login)
        self.assertEqual('adminBMC!', result.passwd)
        self.assertEqual('test-2', result.pcmk_host_list)
