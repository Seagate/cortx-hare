{-
    This provides a convenient import to obtain all available types.

    Users will typically use this import to access constructors for various
    union types, like this:
    ```
    let types = ./types.dhall
    let defaults = ./defaults.dhall
    in    defaults.Config
        ⫽ { role = Some { enable = True, value = types.Role.wizard } }
    ```
    This import is also used internally within the package as a convenient
    import for all available types.
-}

{ Addr        = ./types/Addr.dhall
, Endpoint    = ./types/Endpoint.dhall
, NetId       = ./types/NetId.dhall
, Protocol    = ./types/Protocol.dhall

, ClusterDesc = ./types/ClusterDesc.dhall
, FailVec     = ./types/FailVec.dhall
, PoolDisks   = ./types/PoolDisks.dhall

, Obj         = ./types/Obj.dhall
, ObjT        = ./types/ObjT.dhall
, Oid         = ./types/Oid.dhall
, SvcT        = ./types/SvcT.dhall

, Root        = ./types/Root.dhall
, FdmiFltGrp  = ./types/FdmiFltGrp.dhall
, FdmiFilter  = ./types/FdmiFilter.dhall
-- software subtree
, Node        = ./types/Node.dhall
, Process     = ./types/Process.dhall
, Service     = ./types/Service.dhall
, Sdev        = ./types/Sdev.dhall
-- hardware subtree
, Site        = ./types/Site.dhall
, Rack        = ./types/Rack.dhall
, Enclosure   = ./types/Enclosure.dhall
, Controller  = ./types/Controller.dhall
, Drive       = ./types/Drive.dhall
-- pools subtree
, Pool        = ./types/Pool.dhall
, PoolType    = ./types/PoolType.dhall
, Pver        = ./types/Pver.dhall
, PverF       = ./types/PverF.dhall
, Objv        = ./types/Objv.dhall
, Profile     = ./types/Profile.dhall
}
