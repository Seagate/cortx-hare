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

-- m0d process
let M0Server =
  { runs_confd : Optional Bool
  , io_disks : { meta_data: Optional Text, data : List Text }
  }

let Node =
  { hostname : Text
  , data_iface : Text
  , data_iface_type: Optional ./Protocol.dhall
  , m0_servers : List M0Server
  , m0_clients : { s3 : Natural, other : Natural }
  }

let Pool =
  { name : Text
  , type : Optional ./PoolType.dhall
  , disks : ./PoolDisks.dhall
  , data_units : Natural    -- N
  , parity_units : Natural  -- K
  , allowed_failures : Optional ./FailVec.dhall
  }

in
{ nodes : List Node
, pools : List Pool
-- XXX-TODO: add `profiles` section
}
