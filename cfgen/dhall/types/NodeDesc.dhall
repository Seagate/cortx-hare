{-
  Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  For any questions about this software or licensing,
  please email opensource@seagate.com or cortx-questions@seagate.com.

-}

{ hostname : Text
, node_group: Optional Text 
, machine_id : Optional Text
, processorcount: Optional Natural
, memorysize_mb: Optional Double
, data_iface : Text
, data_iface_ip_addr : Optional Text
, data_iface_type : Optional ./Protocol.dhall
, transport_type : Text
, m0_servers : Optional (List ./M0ServerDesc.dhall)
, m0_clients : Optional (List ./M0ClientDesc.dhall)
, network_ports : Optional ./Ports.dhall
}
