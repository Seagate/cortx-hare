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

let zoid = \(objt : ObjT) -> \(key : Natural) -> mkOid objt 0 key

let Oid/toConfGen = \(x : Oid) ->
    let cont : Text =
        if Natural/isZero x.cont7
        then ""
        else "${Natural/show x.cont7}:"
    in
    "${ObjT/show x.type}-${cont}${Natural/show x.key}"

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
let text = Text/show

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

-- FdmiFilter
let FdmiFilter =
  { id : Natural   -- fid
  , root : Text
  , endpoints : List Text
  }

let FdmiFilter/toConfGen = \(x : FdmiFilter) ->
    "(id=${nat x.id}"
 ++ " root=${text x.root}"
 ++ " endpoints=${join.Texts x.endpoints}"
 ++ ")"

-- FdmiFltGrp
let FdmiFltGrp =
  { rec_type : Natural
  , filters : List Oid
  }

let FdmiFltGrp/toConfGen = \(x : FdmiFltGrp) ->
    "(rec_type=${nat x.rec_type}"
 ++ " filters=${join.Oids x.filters}"
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

-- controller
let Controller =
  { id : Oid
  , node : Oid
  , drives : List Oid
  , pvers :  List Oid
  }

let Controller/toConfGen = \(x : Controller) ->
    "(${oid x.id}"
 ++ " node=${oid x.node}"
 ++ " drives=${join.Oids x.drives}"
 ++ " pvers=${join.Oids x.pvers}"
 ++ ")"

-- drive
let Drive =
  { id : Oid
  , dev : Oid
  , pvers : List Oid
  }

let Drive/toConfGen = \(x : Drive) ->
    "(${oid x.id}"
 ++ " dev=${oid x.dev}"
 ++ " pvers=${join.Oids x.pvers}"
 ++ ")"

-- enclosure
let Enclosure =
  { id : Oid
  , ctrls : List Oid
  , pvers : List Oid
  }

let Enclosure/toConfGen = \(x : Enclosure) ->
    "(${oid x.id}"
 ++ " ctrls=${join.Oids x.ctrls}"
 ++ " pvers=${join.Oids x.pvers}"
 ++ ")"

-- Objv
let Objv =
  { id : Oid
  , real : Oid  -- real
  , children : List Oid
  }

let Objv/toConfGen = \(x : Objv) ->
    "(${oid x.id}"
 ++ " real=${oid x.real}"
 ++ " children=${join.Oids x.children}"
 ++ ")"

-- Pool
let Pool =
  { id : Oid
  , pver_policy : Natural
  , pvers : List Oid
  }

let Pool/toConfGen = \(x : Pool) ->
    "(${oid x.id}"
 ++ " pver_policy=${nat x.pver_policy}"
 ++ " pvers=${join.Oids x.pvers}"
 ++ ")"

-- Profile
let Profile =
  { id : Oid
  , pools : List Oid
  }

let Profile/toConfGen = \(x : Profile) ->
    "(${oid x.id}"
 ++ " pools=${join.Oids x.pools})"

-- Pver
let Pver =
  { id : Oid
  , N : Natural
  , K : Natural
  , P : Natural
  , tolerance : List Natural
  , sitevs : List Oid
  }

let Pver/toConfGen = \(x : Pver) ->
    "(${oid x.id}"
 ++ " N=${nat x.N}"
 ++ " K=${nat x.K}"
 ++ " P=${nat x.P}"
 ++ " tolerance=${join.Naturals x.tolerance}"
 ++ " sitevs=${join.Oids x.sitevs}"
 ++ ")"


-- PverF
let PverF =
  { iD : Oid
  , id : Natural
  , base : Oid
  , allowance : List Natural
  }

let PverF/toConfGen = \(x : PverF) ->
    "(${oid x.iD}"
 ++ " id=${nat x.id}"
 ++ " base=${oid x.base}"
 ++ " allowance=${join.Naturals x.allowance}"
 ++ ")"

-- Rack
let Rack =
  { id : Oid
  , encls : List Oid
  , pvers : List Oid
  }

let Rack/toConfGen = \(x : Rack) ->
    "(${oid x.id}"
 ++ " encls=${join.Oids x.encls}"
 ++ " pvers=${join.Oids x.pvers}"
 ++ ")"

-- Sdev
let Sdev =
  { id : Oid
  , dev_idx : Natural
  , iface : Natural
  , media : Natural
  , bsize : Natural
  , size : Natural
  , last_state : Natural
  , flags : Natural
  , filename : Text
  }

let Sdev/toConfGen = \(x : Sdev) ->
    "(${oid x.id}"
 ++ " dev_idx=${nat x.dev_idx}"
 ++ " iface=${nat x.iface}"
 ++ " media=${nat x.media}"
 ++ " bsize=${nat x.bsize}"
 ++ " size=${nat x.size}"
 ++ " last_state=${nat x.last_state}"
 ++ " flags=${nat x.flags}"
 ++ " filename=${text x.filename}"
 ++ ")"

-- Service
let Service =
  { id : Oid
  , type : Natural
  , endpoints : List Text
  , params : List Text
  , sdevs : List Oid
  }

let Service/toConfGen = \(x : Service) ->
    "(${oid x.id}"
 ++ " type=${nat x.type}"
 ++ " endpoints=${join.Texts x.endpoints}"
 ++ " params=${join.Texts x.params}"
 ++ " sdevs=${join.Oids x.sdevs}"
 ++ ")"

-- Site
let Site =
  { id : Oid
  , racks : List Oid
  , pvers : List Oid
  }

let Site/toConfGen = \(x : Site) ->
    "(${oid x.id}"
 ++ " racks=${join.Oids x.racks}"
 ++ " pvers=${join.Oids x.pvers}"
 ++ ")"

let Obj =
  < Root : Root
  | FdmiFltGrp : FdmiFltGrp
  | FdmiFilter : FdmiFilter
  | Node : Node
  | Process : Process
  | Service : Service
  | Sdev : Sdev
  | Site : Site
  | Rack : Rack
  | Enclosure : Enclosure
  | Controller : Controller
  | Drive : Drive
  | Pool : Pool
  | Pver : Pver
  | PverF : PverF
  | Objv : Objv
  | Profile : Profile
  >

let Obj/toConfGen : Obj -> Text =
    \(x : Obj) ->
    let conv =
      { Root = Root/toConfGen
      , FdmiFltGrp = FdmiFltGrp/toConfGen
      , FdmiFilter = FdmiFilter/toConfGen
      , Node = Node/toConfGen
      , Process = Process/toConfGen
      , Service = Service/toConfGen
      , Sdev = Sdev/toConfGen
      , Site = Site/toConfGen
      , Rack = Rack/toConfGen
      , Enclosure = Enclosure/toConfGen
      , Controller = Controller/toConfGen
      , Drive = Drive/toConfGen
      , Pool = Pool/toConfGen
      , Pver = Pver/toConfGen
      , PverF = PverF/toConfGen
      , Objv = Objv/toConfGen
      , Profile = Profile/toConfGen
      }
    in merge conv x

let Objs/toConfGen = \(objs : List Obj) ->
    Text/concatSep "\n" (List/map Obj Text Obj/toConfGen objs) ++ "\n"

let ids =
  { root       = zoid ObjT.Root 0
  , node       = zoid ObjT.Node 6
  , process_24 = zoid ObjT.Process 24
  , process_27 = zoid ObjT.Process 27
  , process_30 = zoid ObjT.Process 30
  , process_38 = zoid ObjT.Process 38
  , process_40 = zoid ObjT.Process 40
  , process_42 = zoid ObjT.Process 42
  , process_44 = zoid ObjT.Process 44
  , process_45 = zoid ObjT.Process 44
  , process_46 = zoid ObjT.Process 46
  , service_25 = zoid ObjT.Service 25
  , service_26 = zoid ObjT.Service 26
  , service_28 = zoid ObjT.Service 28
  , service_29 = zoid ObjT.Service 29
  , service_31 = zoid ObjT.Service 31
  , service_32 = zoid ObjT.Service 32
  , service_33 = zoid ObjT.Service 33
  , service_34 = zoid ObjT.Service 34
  , service_35 = zoid ObjT.Service 35
  , service_36 = zoid ObjT.Service 36
  , service_37 = zoid ObjT.Service 37
  , service_39 = zoid ObjT.Service 39
  , service_41 = zoid ObjT.Service 41
  , service_43 = zoid ObjT.Service 43
  , service_45 = zoid ObjT.Service 45
  , service_47 = zoid ObjT.Service 47
  , site       = zoid ObjT.Site 3
  , pool_1     = zoid ObjT.Pool 1
  , pool_48    = zoid ObjT.Pool 48
  , pool_69    = zoid ObjT.Pool 69
  , pver_2     = zoid ObjT.Pver 2
  , pver_49    = zoid ObjT.Pver 49
  , pver_63    = zoid ObjT.Pver 63
  , pver_f    = zoid ObjT.PverF 62
  , profile    = zoid ObjT.Profile 77
  , sdev_8     = zoid ObjT.Sdev 8
  , sdev_10    = zoid ObjT.Sdev 10
  , sdev_12    = zoid ObjT.Sdev 12
  , sdev_14    = zoid ObjT.Sdev 14
  , sdev_16    = zoid ObjT.Sdev 16
  , sdev_18    = zoid ObjT.Sdev 18
  , sdev_20    = zoid ObjT.Sdev 20
  , sdev_22    = zoid ObjT.Sdev 22
  , sdev_70    = zoid ObjT.Sdev 70
  , objv_50    = zoid ObjT.Objv 50
  , objv_51    = zoid ObjT.Objv 51
  , objv_52    = zoid ObjT.Objv 52
  , objv_53    = zoid ObjT.Objv 53
  , objv_54    = zoid ObjT.Objv 54
  , objv_55    = zoid ObjT.Objv 55
  , objv_56    = zoid ObjT.Objv 56
  , objv_57    = zoid ObjT.Objv 57
  , objv_58    = zoid ObjT.Objv 58
  , objv_59    = zoid ObjT.Objv 59
  , objv_60    = zoid ObjT.Objv 60
  , objv_61    = zoid ObjT.Objv 61
  , objv_64    = zoid ObjT.Objv 64
  , objv_65    = zoid ObjT.Objv 65
  , objv_66    = zoid ObjT.Objv 66
  , objv_67    = zoid ObjT.Objv 67
  , objv_68    = zoid ObjT.Objv 68
  , objv_72    = zoid ObjT.Objv 72
  , objv_73    = zoid ObjT.Objv 73
  , objv_74    = zoid ObjT.Objv 74
  , objv_75    = zoid ObjT.Objv 75
  , objv_76    = zoid ObjT.Objv 76
  , drive_9    = zoid ObjT.Drive 9
  , drive_11   = zoid ObjT.Drive 11
  , drive_13   = zoid ObjT.Drive 13
  , drive_15   = zoid ObjT.Drive 15
  , drive_17   = zoid ObjT.Drive 17
  , drive_19   = zoid ObjT.Drive 19
  , drive_21   = zoid ObjT.Drive 21
  , drive_23   = zoid ObjT.Drive 23
  , drive_71   = zoid ObjT.Drive 71
  , controller_7 = zoid ObjT.Controller 7
  , enclosure_5  = zoid ObjT.Enclosure 5
  , rack_4       = zoid ObjT.Rack 4
  }

let root = Obj.Root
  { id = ids.root
  , verno = 1
  , rootfid = ids.root
  , mdpool = ids.pool_1
  , imeta_pver = Some ids.pver_2
  , mdredundancy = 1
  , params = [] : List Text
  , nodes = [ids.node]
  , sites = [ids.site]
  , pools = [ids.pool_69, ids.pool_48, ids.pool_1]
  , profiles = [ids.profile]
  , fdmi_flt_grps = [] : List Oid
  }

let node = Obj.Node
  { id = ids.node
  , memsize = 2846
  , nr_cpu = 3
  , last_state = 0
  , flags = 0
  , processes = [ids.process_24, ids.process_44, ids.process_46
                , ids.process_30, ids.process_27, ids.process_38
                , ids.process_42, ids.process_40]
  }

let process_24 = Obj.Process
  { id = ids.process_24
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:34:101"
  , services = [ids.service_26, ids.service_25]
  }

let process_40 = Obj.Process
  { id = ids.process_40
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:41:302"
  , services = [ids.service_41]
  }

let process_42 = Obj.Process
  { id = ids.process_42
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:41:303"
  , services = [ids.service_43]
  }

let process_38 = Obj.Process
  { id = ids.process_38
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:41:301"
  , services = [ids.service_39]
  }

let process_27 = Obj.Process
  { id = ids.process_27
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:44:101"
  , services = [ids.service_28, ids.service_29]
  }

let process_30 = Obj.Process
  { id = ids.process_30
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:41:401"
  , services = [ids.service_31, ids.service_36, ids.service_35, ids.service_33, ids.service_37, ids.service_34, ids.service_32]
  }

let process_46 = Obj.Process
  { id = ids.process_46
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:41:305"
  , services = [ids.service_47]
  }

let process_44 = Obj.Process
  { id = ids.process_44
  , cores = [7]
  , mem_limit_as = 134217728
  , mem_limit_rss = 2914304
  , mem_limit_stack = 2914304
  , mem_limit_memlock = 2914304
  , endpoint = "172.28.128.3@tcp:12345:41:304"
  , services = [ids.service_45]
  }

let sdev_16 = Obj.Sdev
  { id = ids.sdev_16
  , dev_idx = 4
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop5"
  }

let sdev_20 = Obj.Sdev
  { id = ids.sdev_20
  , dev_idx = 6
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop7"
  }

let sdev_12 = Obj.Sdev
  { id = ids.sdev_12
  , dev_idx = 2
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop3"
  }

let sdev_18 = Obj.Sdev
  { id = ids.sdev_18
  , dev_idx = 5
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop6"
  }

let sdev_14 = Obj.Sdev
  { id = ids.sdev_14
  , dev_idx = 3
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop4"
  }

let sdev_22 = Obj.Sdev
  { id = ids.sdev_22
  , dev_idx = 7
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop8"
  }

let sdev_8 = Obj.Sdev
  { id = ids.sdev_8
  , dev_idx = 0
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop1"
  }

let sdev_10 = Obj.Sdev
  { id = ids.sdev_10
  , dev_idx = 1
  , iface = 2
  , media = 1
  , bsize = 4096
  , size = 68719476736
  , last_state = 0
  , flags = 0
  , filename = "/dev/loop2"
  }

let sdev_70 = Obj.Sdev
  { id = ids.sdev_70
  , dev_idx = 8
  , iface = 2
  , media = 1
  , bsize = 1
  , size = 1024
  , last_state = 0
  , flags = 0
  , filename = "/dev/null"
  }

let drive_15 = Obj.Drive
  { id = ids.drive_15
  , dev = ids.sdev_14
  , pvers = [ids.pver_49]
  }

let drive_13 = Obj.Drive
  { id = ids.drive_13
  , dev = ids.sdev_12
  , pvers = [ids.pver_49]
  }

let drive_11 = Obj.Drive
  { id = ids.drive_11
  , dev = ids.sdev_10
  , pvers = [ids.pver_49]
  }

let drive_9 = Obj.Drive
  { id = ids.drive_9
  , dev = ids.sdev_8
  , pvers = [ids.pver_49]
  }

let drive_23 = Obj.Drive
  { id = ids.drive_23
  , dev = ids.sdev_22
  , pvers = [ids.pver_49]
  }

let drive_71 = Obj.Drive
  { id = ids.drive_71
  , dev = ids.sdev_70
  , pvers = [ids.pver_2]
  }

let drive_21 = Obj.Drive
  { id = ids.drive_21
  , dev = ids.sdev_20
  , pvers = [ids.pver_49]
  }

let drive_19 = Obj.Drive
  { id = ids.drive_19
  , dev = ids.sdev_18
  , pvers = [ids.pver_49]
  }

let drive_17 = Obj.Drive
  { id = ids.drive_17
  , dev = ids.sdev_16
  , pvers = [ids.pver_49 , ids.pver_63]
  }

let objv_64 = Obj.Objv
  { id = ids.objv_64
  , real = ids.drive_17
  , children = [] : List Oid
  }

let objv_65 = Obj.Objv
  { id = ids.objv_65
  , real = ids.controller_7
  , children = [ids.objv_64]
  }

let objv_66 = Obj.Objv
  { id = ids.objv_66
  , real = ids.enclosure_5
  , children = [ids.objv_65]
  }

let objv_67 = Obj.Objv
  { id = ids.objv_67
  , real = ids.rack_4
  , children = [ids.objv_66]
  }

let objv_68 = Obj.Objv
  { id = ids.objv_68
  , real = ids.site
  , children = [ids.objv_67]
  }

let objv_61 = Obj.Objv
  { id = ids.objv_61
  , real = ids.drive_23
  , children = [] : List Oid
  }

let objv_60 = Obj.Objv
  { id = ids.objv_60
  , real = ids.drive_21
  , children = [] : List Oid
  }

let objv_59 = Obj.Objv
  { id = ids.objv_59
  , real = ids.drive_19
  , children = [] : List Oid
  }

let objv_58 = Obj.Objv
  { id = ids.objv_58
  , real = ids.drive_17
  , children = [] : List Oid
  }

let objv_57 = Obj.Objv
  { id = ids.objv_57
  , real = ids.drive_15
  , children = [] : List Oid
  }

let objv_56 = Obj.Objv
  { id = ids.objv_56
  , real = ids.drive_13
  , children = [] : List Oid
  }

let objv_55 = Obj.Objv
  { id = ids.objv_55
  , real = ids.drive_11
  , children = [] : List Oid
  }

let objv_50 = Obj.Objv
  { id = ids.objv_50
  , real = ids.drive_9
  , children = [] : List Oid
  }

let objv_51 = Obj.Objv
  { id = ids.objv_51
  , real = ids.controller_7
  , children = [ids.objv_50, ids.objv_55, ids.objv_56, ids.objv_57, ids.objv_58, ids.objv_59, ids.objv_60, ids.objv_61]
  }

let objv_52 = Obj.Objv
  { id = ids.objv_52
  , real = ids.enclosure_5
  , children = [ids.objv_51]
  }

let objv_53 = Obj.Objv
  { id = ids.objv_53
  , real = ids.rack_4
  , children = [ids.objv_52]
  }

let objv_54 = Obj.Objv
  { id = ids.objv_54
  , real = ids.site
  , children = [ids.objv_53]
  }

let objv_72 = Obj.Objv
  { id = ids.objv_72
  , real = ids.drive_71
  , children = [] : List Oid
  }

let objv_73 = Obj.Objv
  { id = ids.objv_73
  , real = ids.controller_7
  , children = [ids.objv_72]
  }

let objv_74 = Obj.Objv
  { id = ids.objv_74
  , real = ids.enclosure_5
  , children = [ids.objv_73]
  }

let objv_75 = Obj.Objv
  { id = ids.objv_75
  , real = ids.rack_4
  , children = [ids.objv_74]
  }

let objv_76 = Obj.Objv
  { id = ids.objv_76
  , real = ids.site
  , children = [ids.objv_75]
  }

let pver_63 = Obj.Pver
  { id = ids.pver_63
  , N = 1
  , K = 0
  , P = 1
  , tolerance = [0, 0, 0, 1, 0]
  , sitevs = [ids.objv_68]
  }

let pver_49 = Obj.Pver
  { id = ids.pver_49
  , N = 2
  , K = 1
  , P = 8
  , tolerance = [0, 0, 0, 0, 1]
  , sitevs = [ids.objv_54]
  }

let pver_2 = Obj.Pver
  { id = ids.pver_2
  , N = 1
  , K = 0
  , P = 1
  , tolerance = [0, 0, 0, 1, 0]
  , sitevs = [ids.objv_76]
  }

let pool_48 = Obj.Pool
  { id = ids.pool_48
  , pver_policy = 0
  , pvers = [ids.pver_f, ids.pver_49]
  }

let pool_69 = Obj.Pool
  { id = ids.pool_69
  , pver_policy = 0
  , pvers = [ids.pver_2]
  }

let pool_1 = Obj.Pool
  { id = ids.pool_1
  , pver_policy = 0
  , pvers = [ids.pver_63]
  }

let service_41 = Obj.Service
  { id = ids.service_41
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:41:302\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_43 = Obj.Service
  { id = ids.service_43
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:41:303\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_39 = Obj.Service
  { id = ids.service_39
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:41:301\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_29 = Obj.Service
  { id = ids.service_29
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:44:101\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_28 = Obj.Service
  { id = ids.service_28
  , type = 3
  , endpoints = ["\"172.28.128.3@tcp:12345:44:101\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_32 = Obj.Service
  { id = ids.service_32
  , type = 2
  , endpoints = ["\"172.28.128.3@tcp:12345:41:401\""]
  , params = [] : List Text
  , sdevs = [ids.sdev_10, ids.sdev_22, ids.sdev_16, ids.sdev_8, ids.sdev_14, ids.sdev_18, ids.sdev_12, ids.sdev_20]
  }

let service_34 = Obj.Service
  { id = ids.service_34
  , type = 9
  , endpoints = ["\"172.28.128.3@tcp:12345:41:401\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_37 = Obj.Service
  { id = ids.service_37
  , type = 21
  , endpoints = ["\"172.28.128.3@tcp:12345:41:401\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_33 = Obj.Service
  { id = ids.service_33
  , type = 8
  , endpoints = ["\"172.28.128.3@tcp:12345:41:401\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_35 = Obj.Service
  { id = ids.service_35
  , type = 10
  , endpoints = ["\"172.28.128.3@tcp:12345:41:401\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_36 = Obj.Service
  { id = ids.service_36
  , type = 11
  , endpoints = ["\"172.28.128.3@tcp:12345:41:401\""]
  , params = [] : List Text
  , sdevs = [ids.sdev_70]
  }

let service_31 = Obj.Service
  { id = ids.service_31
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:41:401\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_45 = Obj.Service
  { id = ids.service_45
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:41:304\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_47 = Obj.Service
  { id = ids.service_47
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:41:305\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_25 = Obj.Service
  { id = ids.service_25
  , type = 6
  , endpoints = ["\"172.28.128.3@tcp:12345:34:101\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let service_26 = Obj.Service
  { id = ids.service_26
  , type = 4
  , endpoints = ["\"172.28.128.3@tcp:12345:34:101\""]
  , params = [] : List Text
  , sdevs = [] : List Oid
  }

let controller_7 = Obj.Controller
  { id = ids.controller_7
  , node = ids.node
  , drives = [ids.drive_17, ids.drive_19, ids.drive_21, ids.drive_71, ids.drive_23, ids.drive_9, ids.drive_11, ids.drive_13, ids.drive_15]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let enclosure_5 = Obj.Enclosure
  { id = ids.enclosure_5
  , ctrls = [ids.controller_7]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let rack_4 = Obj.Rack
  { id = ids.rack_4
  , encls = [ids.enclosure_5]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let site = Obj.Site
  { id = ids.site
  , racks = [ids.rack_4]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let pver_f = Obj.PverF
  { iD = ids.pver_f
  , id = 0
  , base = ids.pver_49
  , allowance = [0, 0, 0, 0, 1]
  }

let profile_77 = Obj.Profile
  { id = ids.profile
  , pools = [ids.pool_69, ids.pool_48, ids.pool_1]
  }

let objs = [controller_7,
	     enclosure_5,
             rack_4,
             root,
             node,
             process_24,
             process_27,
             process_30,
             process_38,
             process_40,
             process_42,
             process_44,
             process_46,
             service_25,
             service_26,
             service_28,
             service_29,
             service_31,
             service_32,
             service_33,
             service_34,
             service_35,
             service_36,
             service_37,
             service_39,
             service_41,
             service_43,
             service_45,
             service_47,
             pool_1,
             pool_48,
             pool_69,
             pver_2,
             pver_49,
             pver_63,
             sdev_8,
             sdev_10,
             sdev_12,
             sdev_14,
             sdev_16,
             sdev_18,
             sdev_20,
             sdev_22,
             sdev_70,
             drive_11,
             drive_13,
             drive_15,
             drive_17,
             drive_19,
             drive_21,
             drive_23,
             drive_71,
             objv_50,
             objv_51,
             objv_52,
             objv_53,
             objv_54,
             objv_55,
             objv_56,
             objv_57,
             objv_58,
             objv_59,
             objv_60,
             objv_61,
             objv_65,
             objv_66,
             objv_67,
             objv_68,
             objv_72,
             objv_73,
             objv_74,
             objv_75,
             objv_76,
	     pver_f,
             profile_77,
             site]

in Objs/toConfGen objs
