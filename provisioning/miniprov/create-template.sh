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

conf $URL set 'cluster>server_nodes>SOME_ID=srvnode_1'
conf $URL set 'cluster>srvnode_1>hostname=myhost'
conf $URL set 'cluster>srvnode_1>network>data>interface_type=tcp'
conf $URL set 'cluster>srvnode_1>storage>data_devices[0]=/dev/sdb'
conf $URL set 'cluster>srvnode_1>network>data>private_interfaces[0]=eth1'
conf $URL set 'cluster>srvnode_1>network>data>private_interfaces[1]=eno2'
conf $URL set 'cluster>srvnode_1>storage>metadata_devices[0]=/dev/meta'
conf $URL set 'cluster>srvnode_1>s3_instances=1'
