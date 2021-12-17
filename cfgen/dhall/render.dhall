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

{ LnetEndpoint   = ./render/LnetEndpoint.dhall
, NetId      = ./render/NetId.dhall

, LibfabricEndpoint = ./render/LibfabricEndpoint.dhall
, NetFamily   = ./types/NetFamily.dhall

, Obj        = ./render/Obj.dhall
, Objs       = ./render/Objs.dhall
, ObjT       = ./render/ObjT.dhall
, Oid        = ./render/Oid.dhall
, SvcT       = ./render/SvcT.dhall

, Root       = ./render/Root.dhall
, FdmiFilter = ./render/FdmiFilter.dhall
, FdmiFltGrp = ./render/FdmiFltGrp.dhall
-- software subtree
, Node       = ./render/Node.dhall
, Process    = ./render/Process.dhall
, Service    = ./render/Service.dhall
, Sdev       = ./render/Sdev.dhall
-- hardware subtree
, Site       = ./render/Site.dhall
, Rack       = ./render/Rack.dhall
, Enclosure  = ./render/Enclosure.dhall
, Controller = ./render/Controller.dhall
, Drive      = ./render/Drive.dhall
-- pools subtree
, Pool       = ./render/Pool.dhall
, Pver       = ./render/Pver.dhall
, PverF      = ./render/PverF.dhall
, Objv       = ./render/Objv.dhall
, Profile    = ./render/Profile.dhall
}
