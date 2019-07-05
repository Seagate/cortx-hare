let NetProtocol =
  < Loopback
  | Tcp : Optional Natural         -- optional digit after "@tcp"
  | Infiniband : Optional Natural  -- optional digit after "@o2ib"
  >

-- Lnet endpoint.
--
-- Endpoint address format (ABNF):
--
-- endpoint = nid ":12345:" DIGIT+ ":" DIGIT+
-- ; <network id>:<process id>:<portal number>:<transfer machine id>
-- ;
-- nid      = "0@lo" / (ipv4addr  "@" ("tcp" / "o2ib") [DIGIT])
-- ipv4addr = 1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT ; 0..255
let Endpoint =
  { lnet_proto : NetProtocol
  , lnet_portal : Natural
  , lnet_tmid : Natural
  }

-- m0d
let M0Server =
  { endpoint : Endpoint
  , runs_confd : Bool      -- whether to run confd on this m0d
  , io_disks :
      { path_regex : Text  -- if not empty, the m0d will run an IO service
      }
  }

let Host =
  { name : Text  -- hostname
  , disks : { path_glob : Text }  -- disks which may be used by Mero
  , m0_servers : List M0Server    -- m0d processes
  , c0_clients : List Endpoint    -- clovis applications
  , m0t1fs_clients : List Endpoint
  }

let PoolDisks =
  < All
  | Select : List { host : Text, path_regex : Text }
  >

let Pool =
  { name : Text
  , disks : PoolDisks
  , data_units : Natural    -- N
  , parity_units : Natural  -- K
  , allowed_failures :
      { ctrl : Natural, disk : Natural }  -- site = rack = encl = 0
  }

let Cluster =
  { hosts : List Host
  , pools : List Pool
  }

in
  { hosts =
      [ { name = "localhost"
        , disks = { path_glob = "/dev/loop[0-9]*" }
        , m0_servers =
            [ { endpoint =
                  { lnet_proto = NetProtocol.Loopback
                  , lnet_portal = 34
                  , lnet_tmid = 101
                  }
              , runs_confd = True
              , io_disks = { path_regex = "." }
              }
            ]
        , c0_clients = [] : List Endpoint
        , m0t1fs_clients = [] : List Endpoint
        }
      ]
  , pools =
      [ { name = "the pool"
        , disks = PoolDisks.All
        , data_units = 1
        , parity_units = 0
        , allowed_failures = { ctrl = 0, disk = 0 }
        }
      ]
  } : Cluster
