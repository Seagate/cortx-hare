let types = ../dhall/types.dhall

in
{ nodes =
    [ { hostname = "localhost"
      , data_iface = "eth1"
      , m0_servers =
          [ { runs_confd = Some True
            , io_disks = None { path_glob : Text }
            }
          , { runs_confd = None Bool
            , io_disks = Some { path_glob = "/dev/loop[0-9]*" }
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
