{-*- dhall -*-}

let Endpoint = ../../Endpoint/Endpoint
let Oid      = ../Oid/Oid
let SvcT     = ../SvcT/SvcT

-- m0_confx_root
let Root =
  { id : Oid
  , mdpool : Oid
  , imeta_pver : Optional Oid
  , nodes : List Oid
  , sites : List Oid
  , pools : List Oid
  , profiles : List Oid
  }

-- m0_confx_fdmi_flt_grp
let FdmiFltGrp =
  { id : Oid
  , rec_type : Natural
  , filters : List Oid  -- XXX s/Oid/Fid/
  }

-- m0_confx_fdmi_filter
let FdmiFilter =
  { id : Oid
  , filter_id : Oid  -- XXX s/Oid/Fid/
  , filter_root : Text
  , node : Oid  -- XXX s/Oid/Fid/
  , endpoints : List Text
  }

-- m0_confx_node
let Node =
  { id : Oid
  , nr_cpu : Natural
  , memsize_MB : Natural
  , processes : List Oid
  }

-- m0_confx_process
let Process =
  { id : Oid
  , nr_cpu : Natural
  , memsize_MB : Natural
  , endpoint : Endpoint
  , services : List Oid
  }

-- m0_confx_service
let Service =
  { id : Oid
  , type : SvcT
  , endpoint : Endpoint
  , sdevs : List Oid
  }

-- m0_confx_sdev
let Sdev =
  { id : Oid
  , dev_idx : Natural
  , iface : Natural  -- XXX make it a union
  , media : Natural  -- XXX make it a union
  , bsize : Natural
  , size : Natural
  , filename : Text
  }

-- m0_confx_site
let Site =
  { id : Oid
  , racks : List Oid
  , pvers : List Oid
  }

-- m0_confx_rack
let Rack =
  { id : Oid
  , encls : List Oid
  , pvers : List Oid
  }

-- m0_confx_enclosure
let Enclosure =
  { id : Oid
  , ctrls : List Oid
  , pvers : List Oid
  }

-- m0_confx_controller
let Controller =
  { id : Oid
  , node : Oid
  , drives : List Oid
  , pvers :  List Oid
  }

-- m0_confx_drive
let Drive =
  { id : Oid
  , sdev : Oid
  , pvers : List Oid
  }

-- m0_confx_pool
let Pool =
  { id : Oid
  , pvers : List Oid
  }

-- m0_confx_pver_actual
let Pver =
  { id : Oid
  , N : Natural
  , K : Natural
  , P : Natural
  , tolerance : List Natural
  , sitevs : List Oid
  }

-- m0_confx_pver_formulaic
let PverF =
  { id : Oid
  , cuid : Natural  -- cluster-unique identifier of this formulaic pver
  , base : Oid
  , allowance : List Natural
  }

-- m0_confx_objv
let Objv =
  { id : Oid
  , real : Oid
  , children : List Oid
  }

-- m0_confx_profile
let Profile =
  { id : Oid
  , pools : List Oid
  }

in
{ Root = Root
, FdmiFltGrp = FdmiFltGrp
, FdmiFilter = FdmiFilter
-- software subtree
, Node = Node
, Process = Process
, Service = Service
, Sdev = Sdev
-- hardware subtree
, Site = Site
, Rack = Rack
, Enclosure = Enclosure
, Controller = Controller
, Drive = Drive
-- pool subtree
, Pool = Pool
, Pver = Pver
, PverF = PverF
, Objv = Objv
, Profile = Profile
}
