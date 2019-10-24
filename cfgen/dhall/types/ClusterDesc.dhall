-- m0d
let M0Server =
  { runs_confd : Optional Bool  -- whether to run confd on this m0d
  , io_disks : Optional { path_glob : Text }
  }

-- m0_client
let C0Client =
  { s3 : Natural    -- max qty of S3 servers this host may run
  , other : Natural -- max qty of other Clovis apps this host may have
  }

let Host =
  { name : Text   -- hostname
  , data_iface : Optional Text  -- data interface
  , m0_servers : List M0Server  -- m0d processes
  , m0_clients : C0Client  -- clovis client processes
  }

let Pool =
  { name : Text
  , disks : ./PoolDisks.dhall
  , data_units : Natural    -- N
  , parity_units : Natural  -- K
  , allowed_failures : Optional ./FailVec.dhall
  }

in
{ hosts : List Host
, pools : List Pool
-- XXX-TODO: add `profiles` section
}
