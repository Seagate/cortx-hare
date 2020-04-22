let Prelude = ../dhall/Prelude.dhall
let types = ../dhall/types.dhall

in
{ nodes =
    [ { hostname = "localhost"
      , data_iface = "eth1"
      , data_iface_type = None types.Protocol
      , m0_servers =
          [ { runs_confd = Some True
            , io_disks = [] : List Text
            }
          , { runs_confd = None Bool
            , io_disks =
                let mkPath = \(i : Natural) -> "/dev/loop" ++ Natural/show i
                in Prelude.List.generate 10 Text mkPath
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
      , disks = types.PoolDisks.all
      , data_units = 1
      , parity_units = 0
      , allowed_failures = None types.FailVec
      }
    ]
} : types.ClusterDesc
