# flake8: noqa
import unittest
import sys
sys.path.insert(0, '..')
from pcswrap.internal.connector import CliExecutor, CliConnector
from pcswrap.exception import PcsNoStatusException
from pcswrap.client import Client
from unittest.mock import Mock, MagicMock

GOOD_XML = '''<?xml version="1.0"?>
<crm_mon version="1.1.20">
    <summary>
        <stack type="corosync" />
        <current_dc present="true" version="1.1.20-5.el7_7.1-3c4c782f70" name="smc8-m11" id="2" with_quorum="true" />
        <last_update time="Wed Feb 26 14:07:26 2020" />
        <last_change time="Tue Feb 25 20:08:36 2020" user="root" client="cibadmin" origin="smc7-m11" />
        <nodes_configured number="2" expected_votes="unknown" />
        <resources_configured number="6" disabled="0" blocked="0" />
        <cluster_options stonith-enabled="false" symmetric-cluster="true" no-quorum-policy="ignore" maintenance-mode="false" />
    </summary>
    <nodes>
        <node name="smc7-m11" id="1" online="true" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="true" is_dc="false" resources_running="3" type="member" />
        <node name="smc8-m11" id="2" online="false" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="true" is_dc="true" resources_running="3" type="member" />
    </nodes>
    <resources>
        <clone id="lnet-clone" multi_state="false" unique="false" managed="true" failed="false" failure_ignored="false" >
            <resource id="lnet" resource_agent="systemd:lnet" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                <node name="smc8-m11" id="2" cached="false"/>
            </resource>
            <resource id="lnet" resource_agent="systemd:lnet" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                <node name="smc7-m11" id="1" cached="false"/>
            </resource>
        </clone>
        <group id="c1" number_resources="2" >
             <resource id="ip-c1" resource_agent="ocf::heartbeat:IPaddr2" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                 <node name="smc7-m11" id="1" cached="false"/>
             </resource>
             <resource id="lnet-c1" resource_agent="ocf::seagate:lnet" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                 <node name="smc7-m11" id="1" cached="false"/>
             </resource>
        </group>
        <group id="c2" number_resources="2" >
             <resource id="ip-c2" resource_agent="ocf::heartbeat:IPaddr2" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                 <node name="smc8-m11" id="2" cached="false"/>
             </resource>
             <resource id="lnet-c2" resource_agent="ocf::seagate:lnet" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                 <node name="smc8-m11" id="2" cached="false"/>
             </resource>
        </group>
    </resources>
    <node_attributes>
        <node name="smc7-m11">
        </node>
        <node name="smc8-m11">
        </node>
    </node_attributes>
    <node_history>
        <node name="smc8-m11">
            <resource_history id="ip-c2" orphan="false" migration-threshold="1000000">
                <operation_history call="29" task="start" last-rc-change="Tue Feb 25 19:55:33 2020" last-run="Tue Feb 25 19:55:33 2020" exec-time="107ms" queue-time="0ms" rc="0" rc_text="ok" />
                <operation_history call="30" task="monitor" interval="30000ms" last-rc-change="Tue Feb 25 19:55:33 2020" exec-time="63ms" queue-time="0ms" rc="0" rc_text="ok" />
            </resource_history>
            <resource_history id="lnet" orphan="false" migration-threshold="1000000">
                <operation_history call="15" task="probe" last-rc-change="Tue Feb 25 19:55:27 2020" last-run="Tue Feb 25 19:55:27 2020" exec-time="4ms" queue-time="0ms" rc="0" rc_text="ok" />
                <operation_history call="25" task="start" last-rc-change="Tue Feb 25 19:55:31 2020" last-run="Tue Feb 25 19:55:31 2020" exec-time="2117ms" queue-time="0ms" rc="0" rc_text="ok" />
                <operation_history call="28" task="monitor" interval="60000ms" last-rc-change="Tue Feb 25 19:55:33 2020" exec-time="1ms" queue-time="0ms" rc="0" rc_text="ok" />
            </resource_history>
            <resource_history id="lnet-c2" orphan="false" migration-threshold="1000000">
                <operation_history call="31" task="start" last-rc-change="Tue Feb 25 19:55:33 2020" last-run="Tue Feb 25 19:55:33 2020" exec-time="42ms" queue-time="0ms" rc="0" rc_text="ok" />
                <operation_history call="32" task="monitor" interval="30000ms" last-rc-change="Tue Feb 25 19:55:33 2020" exec-time="22ms" queue-time="0ms" rc="0" rc_text="ok" />
            </resource_history>
        </node>
        <node name="smc7-m11">
            <resource_history id="ip-c1" orphan="false" migration-threshold="1000000">
                <operation_history call="61" task="start" last-rc-change="Tue Feb 25 20:08:36 2020" last-run="Tue Feb 25 20:08:36 2020" exec-time="80ms" queue-time="0ms" rc="0" rc_text="ok" />
                <operation_history call="62" task="monitor" interval="30000ms" last-rc-change="Tue Feb 25 20:08:36 2020" exec-time="49ms" queue-time="0ms" rc="0" rc_text="ok" />
            </resource_history>
            <resource_history id="lnet" orphan="false" migration-threshold="1000000">
                <operation_history call="15" task="probe" last-rc-change="Tue Feb 25 19:55:27 2020" last-run="Tue Feb 25 19:55:27 2020" exec-time="4ms" queue-time="0ms" rc="0" rc_text="ok" />
                <operation_history call="25" task="start" last-rc-change="Tue Feb 25 19:55:31 2020" last-run="Tue Feb 25 19:55:31 2020" exec-time="2097ms" queue-time="1ms" rc="0" rc_text="ok" />
                <operation_history call="28" task="monitor" interval="60000ms" last-rc-change="Tue Feb 25 19:55:33 2020" exec-time="2ms" queue-time="0ms" rc="0" rc_text="ok" />
            </resource_history>
            <resource_history id="lnet-c1" orphan="false" migration-threshold="1000000">
                <operation_history call="63" task="start" last-rc-change="Tue Feb 25 20:08:36 2020" last-run="Tue Feb 25 20:08:36 2020" exec-time="35ms" queue-time="0ms" rc="0" rc_text="ok" />
                <operation_history call="64" task="monitor" interval="30000ms" last-rc-change="Tue Feb 25 20:08:36 2020" exec-time="20ms" queue-time="0ms" rc="0" rc_text="ok" />
            </resource_history>
        </node>
    </node_history>
    <fence_history>
    </fence_history>
    <tickets>
    </tickets>
    <bans>
    </bans>
</crm_mon>
'''

GOOD_STATUS_TEXT = '''Cluster name: mycluster

WARNINGS:
No stonith devices and stonith-enabled is not false

Stack: corosync
Current DC: ssc-vm-0018 (version 1.1.20-5.el7_7.2-3c4c782f70) - partition with quorum
Last updated: Fri Feb 28 04:25:41 2020
Last change: Fri Feb 28 02:24:06 2020 by hacluster via crmd on ssc-vm-0018

1 node configured
0 resources configured

Online: [ ssc-vm-0018 ]

No resources


Daemon Status:
  corosync: active/disabled
  pacemaker: active/disabled
  pcsd: active/disabled
'''


class PcsExecutorTest(unittest.TestCase):
    def test_get_nodes_works(self):

        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        nodes = connector.get_nodes()
        self.assertEqual(2, len(nodes))

    def test_node_online_parsed_correctly(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        nodes = connector.get_nodes()
        self.assertEqual(2, len(nodes))
        self.assertTrue(nodes[0].online)
        self.assertFalse(nodes[1].online)

    def test_broken_xml_causes_exception(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock(side_effect=['broken'])
        connector = CliConnector(executor=stub_executor)
        with self.assertRaises(PcsNoStatusException):
            connector.get_nodes()

    def test_get_cluster_name_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_status_text = MagicMock(
            side_effect=[GOOD_STATUS_TEXT])
        connector = CliConnector(executor=stub_executor)
        self.assertEqual('mycluster', connector.get_cluster_name())


class ClientTest(unittest.TestCase):
    def test_get_nodes_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        client = Client(connector=connector)

        nodes = client.get_all_nodes()
        self.assertEqual(2, len(nodes))

    def test_get_online_nodes_works(self):
        stub_executor = CliExecutor()
        stub_executor.get_full_status_xml = MagicMock()
        stub_executor.get_full_status_xml.return_value = GOOD_XML

        connector = CliConnector(executor=stub_executor)
        client = Client(connector=connector)

        nodes = client.get_online_nodes()
        self.assertEqual(1, len(nodes))
