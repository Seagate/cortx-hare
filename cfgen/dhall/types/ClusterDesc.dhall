-- m0d process
let M0Server =
  { runs_confd : Optional Bool
  , io_disks : List Text
  }

let Node =
  { hostname : Text
  , data_iface : Text
  , data_iface_type: Optional ./Protocol.dhall
  , m0_servers : List M0Server
  , m0_clients : { s3 : Natural, other : Natural }
  }

let Pool =
  { name : Text
  , disks : ./PoolDisks.dhall
  , data_units : Natural    -- N
  , parity_units : Natural  -- K
  , allowed_failures : Optional ./FailVec.dhall
  }

in
{ nodes : List Node
, pools : List Pool
-- XXX-TODO: add `profiles` section
}
