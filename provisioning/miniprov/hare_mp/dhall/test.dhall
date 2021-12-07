{-

This is just an example how gencdf.dhall can be used to generate the CDF.
gencdf exports a function that ingests a shortened description of cluster (currently shipped as single type NodeInfo). As a result it issues a ClusterDesc type that can be transformed to CDF yaml file like this:

$ dhall <<< ./test.dhall  | dhall-to-yaml >mycdf.yaml

This file should be auto-generated from Python land.

-}
let T = ../cfgen/dhall/types.dhall

let P = T.Protocol

let genCdf = ./gencdf.dhall

in  genCdf
      [ { hostname = "google"
        , machine_id = "8efd697708a8f7e428d3fd520c180795"
        , data_iface = "eth3"
        , data_iface_type = P.tcp
        , io_disks = [ "/var/log", "/mnt/testme" ]
        }
      , { hostname = "srvnode-1"
        , machine_id = "8efd697708a8f7e428d3fd520c180796"
        , data_iface = "eth1"
        , data_iface_type = P.o2ib
        , io_disks =
            [ "/dev/disk/by-id/dm-name-mpatha"
            , "/dev/disk/by-id/dm-name-mpathb"
            , "/dev/disk/by-id/dm-name-mpathc"
            , "/dev/disk/by-id/dm-name-mpathd"
            , "/dev/disk/by-id/dm-name-mpathe"
            , "/dev/disk/by-id/dm-name-mpathf"
            ]
        }
      ]
