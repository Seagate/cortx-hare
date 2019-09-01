let types = ../types.dhall

in
  \(x : types.ObjT) ->
  merge
  { Root       = "root"
  , FdmiFltGrp = "fdmi_flt_grp"
  , FdmiFilter = "fdmi_filter"
  -- software subtree
  , Node       = "node"
  , Process    = "process"
  , Service    = "service"
  , Sdev       = "sdev"
  -- hardware subtree
  , Site       = "site"
  , Rack       = "rack"
  , Enclosure  = "enclosure"
  , Controller = "controller"
  , Drive      = "drive"
  -- pools subtree
  , Pool       = "pool"
  , Pver       = "pver"
  , PverF      = "pver_f"
  , Objv       = "objv"
  , Profile    = "profile"
  }
  x
