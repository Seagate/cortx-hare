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
\(x : types.Root) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ renderOid x.id
      , named.Natural "verno" 1
      , named.Oid "rootfid" x.id
      , named.Oid "mdpool" x.mdpool
      , named.TextUnquoted "imeta_pver"
            (Optional/fold types.Oid x.imeta_pver Text renderOid "(0,0)")
      , named.Natural "mdredundancy" 1  -- XXX Is this value OK for EES?
                                        --     Check with @madhav.
      , "params=[]"
      , named.Oids "nodes" x.nodes
      , named.Oids "sites" x.sites
      , named.Oids "pools" x.pools
      , named.Oids "profiles" x.profiles
      , "fdmi_flt_grps=[]"
      ]
 ++ ")"
