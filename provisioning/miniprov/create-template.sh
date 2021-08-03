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
URL="json://$(readlink -f "$FILENAME")"

conf "$URL" set 'cluster>TMPL_CLUSTER_ID>site>storage_set_count=TMPL_STORAGESET_COUNT'
conf "$URL" set 'cluster>TMPL_CLUSTER_ID>storage_set[0]>durability>TMPL_POOL_TYPE>data=TMPL_DATA_UNITS_COUNT'
conf "$URL" set 'cluster>TMPL_CLUSTER_ID>storage_set[0]>durability>TMPL_POOL_TYPE>parity=TMPL_PARITY_UNITS_COUNT'
conf "$URL" set 'cluster>TMPL_CLUSTER_ID>storage_set[0]>durability>TMPL_POOL_TYPE>spare=TMPL_SPARE_UNITS_COUNT'
conf "$URL" set 'cluster>TMPL_CLUSTER_ID>storage_set[0]>name=TMPL_STORAGESET_NAME'
conf "$URL" set 'cluster>TMPL_CLUSTER_ID>storage_set[0]>server_nodes[0]=TMPL_MACHINE_ID'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>cluster_id=TMPL_CLUSTER_ID'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>hostname=TMPL_HOSTNAME'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>name=TMPL_SERVER_NODE_NAME'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>network>data>interface_type=TMPL_DATA_INTERFACE_TYPE'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>network>data>private_interfaces[0]=TMPL_PRIVATE_DATA_INTERFACE_1'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>network>data>private_interfaces[1]=TMPL_PRIVATE_DATA_INTERFACE_2'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>s3_instances=TMPL_S3SERVER_INSTANCES_COUNT'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>storage>cvg[0]>data_devices[0]=TMPL_DATA_DEVICE_1'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>storage>cvg[0]>data_devices[1]=TMPL_DATA_DEVICE_2'
conf "$URL" set 'server_node>TMPL_MACHINE_ID>storage>cvg[0]>metadata_devices[0]=TMPL_METADATA_DEVICE'

