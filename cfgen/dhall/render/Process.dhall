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

let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall
let renderOid = ./Oid.dhall

in
\(x : types.Process) ->
    let memsize_KiB = x.memsize_MB * 1024
    in
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Naturals "cores" (Prelude.List.replicate x.nr_cpu Natural 1)
      , "mem_limit_as=134217728"  -- = BE_SEGMENT_SIZE = 128MiB
      , named.Natural "mem_limit_rss" memsize_KiB
      , named.Natural "mem_limit_stack" memsize_KiB
      , named.Natural "mem_limit_memlock" memsize_KiB
      , named.Text "endpoint" (./LibfabricEndpoint.dhall x.endpoint)
      , named.Oids "services" x.services
      ]
 ++ ")"
