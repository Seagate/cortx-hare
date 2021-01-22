let Prelude = $path/Prelude.dhall

let T = $path/types.dhall
let P = T.Protocol

let NodeInfo =
      { hostname : Text
      , data_iface : Text
      , data_iface_type : Optional T.Protocol
      , io_disks : List Text
      }

let toNodeDesc
    : NodeInfo -> T.NodeDesc
    =     \(n : NodeInfo)
      ->  { hostname = n.hostname
          , data_iface = n.data_iface
          , data_iface_type = n.data_iface_type
          , m0_clients = { other = 3, s3 = 11 }
          , m0_servers =
              Some
              [ { io_disks = { data = [] : List Text, meta_data = None Text }
                , runs_confd = Some True
                }
              , { io_disks = { data = n.io_disks, meta_data = None Text }
                , runs_confd = None Bool
                }
              ]
          }

let genCdf
    : List NodeInfo -> T.ClusterDesc
    =     \(nodes : List NodeInfo)
      ->  { nodes = Prelude.List.map NodeInfo T.NodeDesc toNodeDesc nodes
          , pools =
              [ { allowed_failures =
                    None
                      { ctrl : Natural
                      , disk : Natural
                      , encl : Natural
                      , rack : Natural
                      , site : Natural
                      }
                , data_units = 1
                , disk_refs = None (List { node : Optional Text, path : Text })
                , name = "the pool"
                , parity_units = 0
                , type = None < dix | md | sns >
                }
              ]
          , profiles = None (List { name : Text, pools : List Text })
          }

in  genCdf
$params
