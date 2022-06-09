let Prelude = $path/Prelude.dhall

let T = $path/types.dhall
let P = T.Protocol
let DiskRef = T.DiskRef


let Disk =
      { path : Optional Text
      , size : Optional Natural
      , blksize : Optional Natural
      }

let IODisks =
      { meta_data : Optional Text
      , data : List Disk
      }

let M0ServerDesc =
      { runs_confd : Optional Bool
      , io_disks : IODisks
      }

let M0ClientDesc =
      { name : Text
      , instances : Natural
      }

let ClientPort =
      { name: Text
      , port: Natural
      }

let ServerPort =
      { name: Text
      , port: Natural
      }

let NodeInfo =
      { hostname : Text
      , machine_id : Optional Text
      , processorcount : Optional Natural
      , memorysize_mb : Optional Double
      , data_iface : Text
      , data_iface_ip_addr : Optional Text
      , data_iface_type : Optional T.Protocol
      , transport_type : Text
      , m0_servers : Optional (List M0ServerDesc)
      , m0_clients : Optional (List M0ClientDesc)
      , network_ports : Optional T.NetworkPorts 
      }

let NodeGroupInfo =
      { name : Text
      , nodes: List NodeInfo
      }

let AllowedFailures =
      { site : Natural
      , rack : Natural
      , encl : Natural
      , ctrl : Natural
      , disk : Natural
      }

let PoolInfo =
      { name : Text
      , disk_refs : Optional (List T.DiskRef)
      , data_units : Natural
      , parity_units : Natural
      , spare_units : Optional Natural
      , type : T.PoolType
      , allowed_failures: Optional AllowedFailures
      }

let ProfileInfo =
      { name : Text
      , pools : List Text
      }

let ClusterInfo =
      { create_aux : Optional Bool
      , node_group_info: List NodeGroupInfo
      , pool_info: List PoolInfo
      , profile_info: List ProfileInfo
      , fdmi_filter_info: Optional (List T.FdmiFilterDesc)
      }

let toNodeGroupDesc
    : NodeGroupInfo -> T.NodeGroupDesc
    =     \(n : NodeGroupInfo)
      ->  { name = n.name
          , nodes = n.nodes
          }

let toPoolDesc
    : PoolInfo -> T.PoolDesc
    =     \(p : PoolInfo)
      ->  { name = p.name
          , type = Some p.type
          , disk_refs = p.disk_refs
          , data_units = p.data_units
          , parity_units = p.parity_units
          , spare_units = p.spare_units
          , allowed_failures = p.allowed_failures
          }

let genCdf
    : ClusterInfo -> T.ClusterDesc
    =     \(cluster_info : ClusterInfo)
      ->  { create_aux = cluster_info.create_aux
          , node_groups = Prelude.List.map NodeGroupInfo T.NodeGroupDesc toNodeGroupDesc cluster_info.node_group_info
          , pools = Prelude.List.map PoolInfo T.PoolDesc toPoolDesc cluster_info.pool_info
          , profiles = Some cluster_info.profile_info
          , fdmi_filters = cluster_info.fdmi_filter_info
          }

in  genCdf
$params
