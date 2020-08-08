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

in
\(x : types.Node) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Natural "memsize" x.memsize_MB
      , named.Natural "nr_cpu" x.nr_cpu
      , named.Natural "last_state" 0
      , named.Natural "flags" 0
      , named.Oids "processes" x.processes
      ]
 ++ ")"
