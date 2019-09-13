{ hosts =
    [ { c0_clients =
          2
      , m0_servers =
          [ { io_disks = None { path_glob : Text }, runs_confd = Some True }
          , { io_disks =
                Some { path_glob = "/dev/loop[0-9]*" }
            , runs_confd =
                None Bool
            }
          ]
      , m0t1fs_clients =
          0
      , name =
          "localhost"
      }
    ]
, pools =
    [ { allowed_failures =
          None
          { ctrl :
              Natural
          , disk :
              Natural
          , encl :
              Natural
          , rack :
              Natural
          , site :
              Natural
          }
      , data_units =
          1
      , disks =
          < all | select : List { host : Text, path_regex : Text } >.all
      , name =
          "the pool"
      , parity_units =
          0
      }
    ]
}
