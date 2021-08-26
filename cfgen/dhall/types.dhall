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

{-
    This provides a convenient import to obtain all available types.

    Users will typically use this import to access constructors for various
    union types, like this:
    ```
    let types = ./types.dhall
    let defaults = ./defaults.dhall
    in    defaults.Config
        ⫽ { role = Some { enable = True, value = types.Role.wizard } }
    ```
    This import is also used internally within the package as a convenient
    import for all available types.
-}

{ Addr        = ./types/Addr.dhall
, Endpoint    = ./types/Endpoint.dhall
, NetId       = ./types/NetId.dhall
, Protocol    = ./types/Protocol.dhall

, LibfabricEndpoint = ./types/LibfabricEndpoint.dhall
, NetFamily   = ./types/NetFamily.dhall

, ClusterDesc  = ./types/ClusterDesc.dhall
, NodeDesc     = ./types/NodeDesc.dhall
, M0ServerDesc = ./types/M0ServerDesc.dhall
, Disk         = ./types/IODisk.dhall
, PoolDesc     = ./types/PoolDesc.dhall
, DiskRef      = ./types/DiskRef.dhall
, FailVec      = ./types/FailVec.dhall
, PoolType     = ./types/PoolType.dhall
, PoolsRef     = ./types/PoolsRef.dhall

, Obj         = ./types/Obj.dhall
, ObjT        = ./types/ObjT.dhall
, Oid         = ./types/Oid.dhall
, SvcT        = ./types/SvcT.dhall

, Root        = ./types/Root.dhall
, FdmiFltGrp  = ./types/FdmiFltGrp.dhall
, FdmiFilter  = ./types/FdmiFilter.dhall
-- software subtree
, Node        = ./types/Node.dhall
, Process     = ./types/Process.dhall
, Service     = ./types/Service.dhall
, Sdev        = ./types/Sdev.dhall
-- hardware subtree
, Site        = ./types/Site.dhall
, Rack        = ./types/Rack.dhall
, Enclosure   = ./types/Enclosure.dhall
, Controller  = ./types/Controller.dhall
, Drive       = ./types/Drive.dhall
-- pools subtree
, Pool        = ./types/Pool.dhall
, Pver        = ./types/Pver.dhall
, PverF       = ./types/PverF.dhall
, Objv        = ./types/Objv.dhall
, Profile     = ./types/Profile.dhall
}
