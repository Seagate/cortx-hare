#!/bin/bash
#
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

set -e -x

FILENAME=$1
URL="json://$(readlink -f $FILENAME)"

conf $URL set 'server_node>SOME_MACHINE_ID>hostname=myhost'
conf $URL set 'server_node>SOME_MACHINE_ID>cluster_id=my-cluster'
conf $URL set 'server_node>SOME_MACHINE_ID>network>data>interface_type=tcp'
conf $URL set 'server_node>SOME_MACHINE_ID>cvg[0]>data_devices[0]=/dev/sda'
conf $URL set 'server_node>SOME_MACHINE_ID>cvg[0]>data_devices[1]=/dev/sdb'
conf $URL set 'server_node>SOME_MACHINE_ID>network>data>private_interfaces[0]=eth1'
conf $URL set 'server_node>SOME_MACHINE_ID>network>data>private_interfaces[1]=eno2'
conf $URL set 'server_node>SOME_MACHINE_ID>cvg[0]>metadata_devices[0]=/dev/meta'
conf $URL set 'server_node>SOME_MACHINE_ID>s3_instances=1'
conf $URL set 'cluster>my-cluster>site>storage_set_count=1'
conf $URL set 'cluster>my-cluster>storage_set1>name=storage1'
conf $URL set 'cluster>my-cluster>storage_set1>server_nodes[0]=SOME_MACHINE_ID'
conf $URL set 'cluster>my-cluster>storage_set1>durability>data=1'
conf $URL set 'cluster>my-cluster>storage_set1>durability>parity=0'
conf $URL set 'cluster>my-cluster>storage_set1>durability>spare=0'

