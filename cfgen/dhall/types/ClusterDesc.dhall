-- m0d
let M0Server =
  { runs_confd : Optional Bool  -- whether to run confd on this m0d
  , io_disks :
      { path_regex : Text  -- empty string means no IO service
      }
  }

let Host =
  { name : Text  -- hostname
  , disks : { path_glob : Text }  -- disks which may be used by Mero
  , m0_servers : List M0Server    -- m0d processes
  , c0_clients : Natural      -- max qty of Clovis apps this host may have
  , m0t1fs_clients : Natural  -- max qty of m0t1fs clients
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
}
