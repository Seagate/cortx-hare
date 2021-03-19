let Prelude = $path/Prelude.dhall

let T = $path/types.dhall
let P = T.Protocol
let DiskRef = T.DiskRef

let NodeInfo =
      { hostname : Text
      , data_iface : Text
      , data_iface_type : Optional T.Protocol
      , io_disks : List Text
      , meta_data : Text
      , s3_instances : Natural
      }

let PoolInfo =
      { name : Text
      , disk_refs : Optional (List T.DiskRef)
      , data_units : Natural
      , parity_units : Natural
      }

let ProfileInfo =
      { name : Text
      , pools : List Text
      }

let ClusterInfo =
      { node_info: List NodeInfo
      , pool_info: List PoolInfo
      , profile_info: List ProfileInfo
      }

let toNodeDesc
    : NodeInfo -> T.NodeDesc
    =     \(n : NodeInfo)
      ->  { hostname = n.hostname
          , data_iface = n.data_iface
          , data_iface_type = n.data_iface_type
          , m0_clients = { other = 3, s3 = n.s3_instances }
          , m0_servers =
              Some
              [ { io_disks = { data = [] : List Text, meta_data = Some n.meta_data }
                , runs_confd = Some True
                }
              , { io_disks = { data = n.io_disks, meta_data = Some n.meta_data }
                , runs_confd = None Bool
                }
              ]
          }

let toPoolDesc
    : PoolInfo -> T.PoolDesc
    =     \(p : PoolInfo)
      ->  { name = p.name
          , type = Some T.PoolType.sns
          , data_units = p.data_units
          , disk_refs = p.disk_refs
          , parity_units = p.parity_units
          , allowed_failures =
                    None
                      { ctrl : Natural
                      , disk : Natural
                      , encl : Natural
                      , rack : Natural
                      , site : Natural
                      }
          }

let genCdf
    : ClusterInfo -> T.ClusterDesc
    =     \(cluster_info : ClusterInfo)
      ->  { nodes = Prelude.List.map NodeInfo T.NodeDesc toNodeDesc cluster_info.node_info
          , pools = Prelude.List.map PoolInfo T.PoolDesc toPoolDesc cluster_info.pool_info
          , profiles = Some cluster_info.profile_info
          }

in  genCdf
$params
