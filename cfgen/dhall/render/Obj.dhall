let types = ../types.dhall
in
  \(x : types.Obj) ->
  merge
  { Root       = ./Root.dhall
  , FdmiFltGrp = ./FdmiFltGrp.dhall
  , FdmiFilter = ./FdmiFilter.dhall
  -- software subtree
  , Node       = ./Node.dhall
  , Process    = ./Process.dhall
  , Service    = ./Service.dhall
  , Sdev       = ./Sdev.dhall
  -- hardware subtree
  , Site       = ./Site.dhall
  , Rack       = ./Rack.dhall
  , Enclosure  = ./Enclosure.dhall
  , Controller = ./Controller.dhall
  , Drive      = ./Drive.dhall
  -- pools subtree
  , Pool       = ./Pool.dhall
  , Pver       = ./Pver.dhall
  , PverF      = ./PverF.dhall
  , Objv       = ./Objv.dhall
  , Profile    = ./Profile.dhall
  }
  x
