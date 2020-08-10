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

let renderAddr = \(label : Text) -> \(addr : types.Addr)
 ->
    let mdigit = Optional/fold Natural addr.mdigit Text Natural/show ""
    in "${addr.ipaddr}@${label}${mdigit}"

in
\(nid : types.NetId) ->
    merge
    { lo = "0@lo"
    , tcp = \(x : { tcp : types.Addr }) -> renderAddr "tcp" x.tcp
    , o2ib = \(x : { o2ib : types.Addr }) -> renderAddr "o2ib" x.o2ib
    }
    nid
