let types = ../dhall/types.dhall

in
{ hosts =
    [ { name = "localhost"
      , m0_servers =
          [ { runs_confd = Some True
            , io_disks = Some { path_glob = "/dev/loop[0-9]*" }
            }
          ]
      , c0_clients = 2
      , m0t1fs_clients = 0
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
