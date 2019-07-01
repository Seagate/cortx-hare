let List/map = https://prelude.dhall-lang.org/List/map
let Text/concatMapSep = https://prelude.dhall-lang.org/Text/concatMapSep
let Text/concatSep = https://prelude.dhall-lang.org/Text/concatSep

let ObjT =
  < Root
  | FdmiFltGrp
  | FdmiFilter
  | Node
  | Process
  | Service
  | Sdev
  | Site
  | Rack
  | Enclosure
  | Controller
  | Drive
  | Pool
  | Pver
  | PverF
  | Objv
  | Profile
  >

let ObjT/show : ObjT -> Text =
    \(x : ObjT) ->
    let conv =
      { Root = "root"
      , FdmiFltGrp = "fdmi_flt_grp"
      , FdmiFilter = "fdmi_filter"
      , Node = "node"
      , Process = "process"
      , Service = "service"
      , Sdev = "sdev"
      , Site = "site"
      , Rack = "rack"
      , Enclosure = "enclosure"
      , Controller = "controller"
      , Drive = "drive"
      , Pool = "pool"
      , Pver = "pver"
      , PverF = "pver_f"
      , Objv = "objv"
      , Profile = "profile"
      }
    in merge conv x

let Oid =
  { type : ObjT
  , cont7 : Natural -- fid.f_container & M0_FID_TYPE_MASK
  , key : Natural
  }

let mkOid = \(type : ObjT) -> \(cont7 : Natural) -> \(key : Natural) ->
    { type = type, cont7 = cont7, key = key } : Oid

let mkOids = \(objT : ObjT) -> \(keys : List Natural) ->
    List/map Natural Oid (mkOid objT 0) keys : List Oid

let Oid/toConfGen = \(x : Oid) ->
    let cont : Text =
        if Natural/isZero x.cont7
        then ""
        else "${Natural/show x.cont7}:"
    in
    "${ObjT/show x.type}-${cont}${Natural/show x.key}"

-- m0_conf_root
let Root =
  { id : Oid
  , verno : Natural
  , rootfid : Oid
  , mdpool : Oid
  , imeta_pver : Optional Oid
  , mdredundancy : Natural
  , params : List Text
  , nodes : List Oid
  , sites : List Oid
  , pools : List Oid
  , profiles : List Oid
  , fdmi_flt_grps : List Oid
  }

let List/toConfGen : forall (a : Type) -> (a -> Text) -> List a -> Text
  = \(a : Type)
 -> \(f : a -> Text)
 -> \(xs : List a)
 ->
    "[" ++ Text/concatMapSep ", " a f xs ++ "]"

let id = \(a : Type) -> \(x : a) -> x

let join =
  { Naturals = List/toConfGen Natural Natural/show
  , Oids = List/toConfGen Oid Oid/toConfGen
  , Texts = List/toConfGen Text (id Text)
  }

let nat = Natural/show
let oid = Oid/toConfGen

let Root/toConfGen = \(x : Root) ->
    let imeta = Optional/fold Oid x.imeta_pver Text oid "(0,0)"
    in
    "(${oid x.id}"
 ++ " verno=${nat x.verno}"
 ++ " rootfid=${oid x.rootfid}"
 ++ " mdpool=${oid x.mdpool}"
 ++ " imeta_pver=${imeta}"
 ++ " mdredundancy=${nat x.mdredundancy}"
 ++ " params=${join.Texts x.params}"
 ++ " nodes=${join.Oids x.nodes}"
 ++ " sites=${join.Oids x.sites}"
 ++ " pools=${join.Oids x.pools}"
 ++ " profiles=${join.Oids x.profiles}"
 ++ " fdmi_flt_grps=${join.Oids x.fdmi_flt_grps}"
 ++ ")"

-- m0_conf_node
let Node =
  { id : Oid
  , memsize : Natural
  , nr_cpu : Natural
  , last_state : Natural
  , flags : Natural
  , processes : List Oid
  }

let Node/toConfGen = \(x : Node) ->
    "(${oid x.id}"
 ++ " memsize=${nat x.memsize}"
 ++ " nr_cpu=${nat x.nr_cpu}"
 ++ " last_state=${nat x.last_state}"
 ++ " flags=${nat x.flags}"
 ++ " processes=${join.Oids x.processes}"
 ++ ")"

-- m0_conf_process
let Process =
  { id : Oid
  , cores : List Natural
  , mem_limit_as : Natural
  , mem_limit_rss : Natural
  , mem_limit_stack : Natural
  , mem_limit_memlock : Natural
  , endpoint : Text
  , services : List Oid
  }

let Process/toConfGen = \(x : Process) ->
    "(${oid x.id}"
 ++ " cores=${join.Naturals x.cores}"
 ++ " mem_limit_as=${nat x.mem_limit_as}"
 ++ " mem_limit_rss=${nat x.mem_limit_rss}"
 ++ " mem_limit_stack=${nat x.mem_limit_stack}"
 ++ " mem_limit_memlock=${nat x.mem_limit_memlock}"
 ++ " endpoint=${Text/show x.endpoint}"
 ++ " services=${join.Oids x.services}"
 ++ ")"

let Obj =
  < Root : Root
  | Node : Node
  | Process : Process
  >

let Obj/toConfGen : Obj -> Text =
    \(x : Obj) ->
    let conv =
      { Root = Root/toConfGen
      , Node = Node/toConfGen
      , Process = Process/toConfGen
      }
    in merge conv x

let Objs/toConfGen = \(objs : List Obj) ->
    Text/concatSep "\n" (List/map Obj Text Obj/toConfGen objs) ++ "\n"

let root : Obj =
    let id = mkOid ObjT.Root 0 0
    in
    Obj.Root
      { id = id
      , verno = 1
      , rootfid = id
      , mdpool = mkOid ObjT.Pool 0 1
      , imeta_pver = Some (mkOid ObjT.Pver 0 2)
      , mdredundancy = 1
      , params = [] : List Text
      , nodes = [ mkOid ObjT.Node 0 6 ]
      , sites = [ mkOid ObjT.Site 0 3 ]
      , pools = mkOids ObjT.Pool [ 69, 48, 1 ]
      , profiles = [ mkOid ObjT.Profile 0 77 ]
      , fdmi_flt_grps = [] : List Oid
      }

let node : Obj =
    Obj.Node
      { id = mkOid ObjT.Node 0 6
      , memsize = 2846
      , nr_cpu = 3
      , last_state = 0
      , flags = 0
      , processes = mkOids ObjT.Process [ 24, 44, 46, 30, 27, 38, 42, 40 ]
      }

let process_24 : Obj =
    Obj.Process
      { id = mkOid ObjT.Process 0 24
      , cores = [7]
      , mem_limit_as = 134217728
      , mem_limit_rss = 2914304
      , mem_limit_stack = 2914304
      , mem_limit_memlock = 2914304
      , endpoint = "172.28.128.3@tcp:12345:34:101"
      , services = mkOids ObjT.Service [ 26, 25 ]
      }

let objs = [ root, node, process_24 ]

in Objs/toConfGen objs
