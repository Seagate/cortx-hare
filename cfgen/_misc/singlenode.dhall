let CD = ./ClusterDesc/package.dhall
in
{ hosts =
    [ { name = "localhost"
      , disks = { path_glob = "/dev/loop[0-9]*" }
      , m0_servers =
          [ { endpoint_fmt =
                -- { proto = CD.NetProtocol.lo
                { proto = CD.NetProtocol.tcp { tcp = None Natural }
                , portal = 34
                , tmid = 101
                }
            , runs_confd = True
            , io_disks = { path_regex = "." }
            }
          ]
      , c0_clients = [] : List CD.EndpointFmt
      , m0t1fs_clients = [] : List CD.EndpointFmt
      }
    ]
, pools =
    [ { name = "the pool"
      , disks = CD.PoolDisks.all
      , data_units = 1
      , parity_units = 0
      , allowed_failures = None CD.FailVec
      }
    ]
} : CD.ClusterDesc
