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

let Prelude = ../dhall/Prelude.dhall
let types = ../dhall/types.dhall

in
{ create_aux = Some False
, nodes =
    [ { hostname = "localhost"
      , machine_id = None Text
      , memorysize_mb = None Double
      , processorcount = None Natural
      , transport_type = "libfab"
      , data_iface = "eth1"
      , data_iface_ip_addr = None Text
      , data_iface_type = None < o2ib | tcp >
      , m0_servers =
          Some
          [ { runs_confd = Some True
            , io_disks =
                { meta_data = None Text
                , data = [] : List
                           { blksize : Optional Natural
                           , path : Optional Text
                           , size : Optional Natural
                           }
                }
            }
          , { runs_confd = None Bool
            , io_disks =
                { meta_data = None Text
                , data =
                    [ { blksize = None Natural
                      , path = Some "/dev/loop0"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop1"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop2"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop3"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop4"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop5"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop6"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop7"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop8"
                      , size = None Natural
                      }
                    , { blksize = None Natural
                      , path = Some "/dev/loop9"
                      , size = None Natural
                      }
                    ]
                }
            }
          ]
      , m0_clients =
          { s3 = 0
          , other = 2
          }
      }
    ]
, pools =
    [ { name = "the pool"
      , type = Some < dix | md | sns >.sns
      , disk_refs = Some
          [ { node = Some "localhost", path = "/dev/loop0" }
          , { node = Some "localhost", path = "/dev/loop1" }
          , { node = Some "localhost", path = "/dev/loop2" }
          , { node = Some "localhost", path = "/dev/loop3" }
          , { node = Some "localhost", path = "/dev/loop4" }
          , { node = Some "localhost", path = "/dev/loop5" }
          , { node = Some "localhost", path = "/dev/loop6" }
          , { node = Some "localhost", path = "/dev/loop7" }
          , { node = Some "localhost", path = "/dev/loop8" }
          , { node = Some "localhost", path = "/dev/loop9" }
          ]
      , data_units = 1
      , parity_units = 0
      , spare_units = Some 0
      , allowed_failures = 
          None
            { ctrl : Natural
            , disk : Natural
            , encl : Natural
            , rack : Natural
            , site : Natural
            }
      }
    ]
, profiles = None (List { name : Text, pools : List Text })
, fdmi_filters =
    None
      ( List
          { client_index : Natural
          , name : Text
          , node : Text
          , substrings : List Text
          }
      )
} : types.ClusterDesc
