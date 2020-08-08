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

let types = ../types.dhall
in
  \(x : types.Obj) ->
  merge
  { Root       = ./Root.dhall
  , FdmiFltGrp = ./FdmiFltGrp.dhall
  , FdmiFilter = ./FdmiFilter.dhall
  -- software subtree
  , Node       = ./Node.dhall
  , Process    = ./Process.dhall
  , Service    = ./Service.dhall
  , Sdev       = ./Sdev.dhall
  -- hardware subtree
  , Site       = ./Site.dhall
  , Rack       = ./Rack.dhall
  , Enclosure  = ./Enclosure.dhall
  , Controller = ./Controller.dhall
  , Drive      = ./Drive.dhall
  -- pools subtree
  , Pool       = ./Pool.dhall
  , Pver       = ./Pver.dhall
  , PverF      = ./PverF.dhall
  , Objv       = ./Objv.dhall
  , Profile    = ./Profile.dhall
  }
  x
