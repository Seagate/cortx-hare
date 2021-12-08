{-
  Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  For any questions about this software or licensing,
  please email opensource@seagate.com or cortx-questions@seagate.com.

-}

let Prelude = ../dhall/Prelude.dhall

let types = ../dhall/types.dhall

let utils = ../dhall/utils.dhall

let toConfGen = ../dhall/toConfGen.dhall

let ids =
    let zoid = utils.zoid
    let ObjT = types.ObjT
    in
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
      , pver_f     = zoid ObjT.PverF 62
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
      , controller = zoid ObjT.Controller 7
      , enclosure  = zoid ObjT.Enclosure 5
      , rack       = zoid ObjT.Rack 4
      }

let root = types.Obj.Root
  { id = ids.root
  , mdpool = ids.pool_1
  , imeta_pver = Some ids.pver_2
  , mdredundancy = 1
  , nodes = [ids.node]
  , sites = [ids.site]
  , pools = [ids.pool_69, ids.pool_48, ids.pool_1]
  , profiles = [ids.profile]
  , fdmi_flt_grps = [] : List types.Oid
  }

let node = types.Obj.Node
  { id = ids.node
  , nr_cpu = 3
  , memsize_MB = 2846
  , processes = [ ids.process_24, ids.process_44, ids.process_46
                , ids.process_30, ids.process_27, ids.process_38
                , ids.process_42, ids.process_40 ]
  }

let endpoints =
    let ep = utils.endpoint types.Protocol.tcp "172.28.128.3"
    in
      { process_24 = ep 34 101
      , process_27 = ep 44 101
      , process_30 = ep 41 401
      , process_38 = ep 41 301
      , process_40 = ep 41 302
      , process_42 = ep 41 303
      , process_44 = ep 41 304
      , process_46 = ep 41 305
      }

let process_24 = types.Obj.Process
  { id = ids.process_24
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_24
  , services = [ids.service_26, ids.service_25]
  }

let process_40 = types.Obj.Process
  { id = ids.process_40
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_40
  , services = [ids.service_41]
  }

let process_42 = types.Obj.Process
  { id = ids.process_42
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_42
  , services = [ids.service_43]
  }

let process_38 = types.Obj.Process
  { id = ids.process_38
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_38
  , services = [ids.service_39]
  }

let process_27 = types.Obj.Process
  { id = ids.process_27
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_27
  , services = [ids.service_28, ids.service_29]
  }

let process_30 = types.Obj.Process
  { id = ids.process_30
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_30
  , services = [ ids.service_31, ids.service_36, ids.service_35
               , ids.service_33, ids.service_37, ids.service_34
               , ids.service_32 ]
  }

let process_44 = types.Obj.Process
  { id = ids.process_44
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_44
  , services = [ids.service_45]
  }

let process_46 = types.Obj.Process
  { id = ids.process_46
  , nr_cpu = 3
  , memsize_MB = 2846
  , endpoint = endpoints.process_46
  , services = [ids.service_47]
  }

let sdev_16 = types.Obj.Sdev
  { id = ids.sdev_16
  , dev_idx = 4
  , filename = "/dev/loop5"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_20 = types.Obj.Sdev
  { id = ids.sdev_20
  , dev_idx = 6
  , filename = "/dev/loop7"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_12 = types.Obj.Sdev
  { id = ids.sdev_12
  , dev_idx = 2
  , filename = "/dev/loop3"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_18 = types.Obj.Sdev
  { id = ids.sdev_18
  , dev_idx = 5
  , filename = "/dev/loop6"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_14 = types.Obj.Sdev
  { id = ids.sdev_14
  , dev_idx = 3
  , filename = "/dev/loop4"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_22 = types.Obj.Sdev
  { id = ids.sdev_22
  , dev_idx = 7
  , filename = "/dev/loop8"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_8 = types.Obj.Sdev
  { id = ids.sdev_8
  , dev_idx = 0
  , filename = "/dev/loop1"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_10 = types.Obj.Sdev
  { id = ids.sdev_10
  , dev_idx = 1
  , filename = "/dev/loop2"
  , size = 68719476736
  , blksize = 4096
  }

let sdev_70 = types.Obj.Sdev
  { id = ids.sdev_70
  , dev_idx = 8
  , filename = "/dev/null"
  , size = 1024
  , blksize = 1
  }

let drive_15 = types.Obj.Drive
  { id = ids.drive_15
  , sdev = ids.sdev_14
  , pvers = [ids.pver_49]
  }

let drive_13 = types.Obj.Drive
  { id = ids.drive_13
  , sdev = ids.sdev_12
  , pvers = [ids.pver_49]
  }

let drive_11 = types.Obj.Drive
  { id = ids.drive_11
  , sdev = ids.sdev_10
  , pvers = [ids.pver_49]
  }

let drive_9 = types.Obj.Drive
  { id = ids.drive_9
  , sdev = ids.sdev_8
  , pvers = [ids.pver_49]
  }

let drive_23 = types.Obj.Drive
  { id = ids.drive_23
  , sdev = ids.sdev_22
  , pvers = [ids.pver_49]
  }

let drive_71 = types.Obj.Drive
  { id = ids.drive_71
  , sdev = ids.sdev_70
  , pvers = [ids.pver_2]
  }

let drive_21 = types.Obj.Drive
  { id = ids.drive_21
  , sdev = ids.sdev_20
  , pvers = [ids.pver_49]
  }

let drive_19 = types.Obj.Drive
  { id = ids.drive_19
  , sdev = ids.sdev_18
  , pvers = [ids.pver_49]
  }

let drive_17 = types.Obj.Drive
  { id = ids.drive_17
  , sdev = ids.sdev_16
  , pvers = [ids.pver_49, ids.pver_63]
  }

let objv_64 = types.Obj.Objv
  { id = ids.objv_64
  , real = ids.drive_17
  , children = [] : List types.Oid
  }

let objv_65 = types.Obj.Objv
  { id = ids.objv_65
  , real = ids.controller
  , children = [ids.objv_64]
  }

let objv_66 = types.Obj.Objv
  { id = ids.objv_66
  , real = ids.enclosure
  , children = [ids.objv_65]
  }

let objv_67 = types.Obj.Objv
  { id = ids.objv_67
  , real = ids.rack
  , children = [ids.objv_66]
  }

let objv_68 = types.Obj.Objv
  { id = ids.objv_68
  , real = ids.site
  , children = [ids.objv_67]
  }

let objv_61 = types.Obj.Objv
  { id = ids.objv_61
  , real = ids.drive_23
  , children = [] : List types.Oid
  }

let objv_60 = types.Obj.Objv
  { id = ids.objv_60
  , real = ids.drive_21
  , children = [] : List types.Oid
  }

let objv_59 = types.Obj.Objv
  { id = ids.objv_59
  , real = ids.drive_19
  , children = [] : List types.Oid
  }

let objv_58 = types.Obj.Objv
  { id = ids.objv_58
  , real = ids.drive_17
  , children = [] : List types.Oid
  }

let objv_57 = types.Obj.Objv
  { id = ids.objv_57
  , real = ids.drive_15
  , children = [] : List types.Oid
  }

let objv_56 = types.Obj.Objv
  { id = ids.objv_56
  , real = ids.drive_13
  , children = [] : List types.Oid
  }

let objv_55 = types.Obj.Objv
  { id = ids.objv_55
  , real = ids.drive_11
  , children = [] : List types.Oid
  }

let objv_50 = types.Obj.Objv
  { id = ids.objv_50
  , real = ids.drive_9
  , children = [] : List types.Oid
  }

let objv_51 = types.Obj.Objv
  { id = ids.objv_51
  , real = ids.controller
  , children = [ ids.objv_50, ids.objv_55, ids.objv_56, ids.objv_57
               , ids.objv_58, ids.objv_59, ids.objv_60, ids.objv_61 ]
  }

let objv_52 = types.Obj.Objv
  { id = ids.objv_52
  , real = ids.enclosure
  , children = [ids.objv_51]
  }

let objv_53 = types.Obj.Objv
  { id = ids.objv_53
  , real = ids.rack
  , children = [ids.objv_52]
  }

let objv_54 = types.Obj.Objv
  { id = ids.objv_54
  , real = ids.site
  , children = [ids.objv_53]
  }

let objv_72 = types.Obj.Objv
  { id = ids.objv_72
  , real = ids.drive_71
  , children = [] : List types.Oid
  }

let objv_73 = types.Obj.Objv
  { id = ids.objv_73
  , real = ids.controller
  , children = [ids.objv_72]
  }

let objv_74 = types.Obj.Objv
  { id = ids.objv_74
  , real = ids.enclosure
  , children = [ids.objv_73]
  }

let objv_75 = types.Obj.Objv
  { id = ids.objv_75
  , real = ids.rack
  , children = [ids.objv_74]
  }

let objv_76 = types.Obj.Objv
  { id = ids.objv_76
  , real = ids.site
  , children = [ids.objv_75]
  }

let pver_63 = types.Obj.Pver
  { id = ids.pver_63
  , data_units = 1
  , parity_units = 0
  , spare_units = 0
  , pool_width = 1
  , tolerance = [0, 0, 0, 1, 0]
  , sitevs = [ids.objv_68]
  }

let pver_49 = types.Obj.Pver
  { id = ids.pver_49
  , data_units = 2
  , parity_units = 1
  , spare_units = 1
  , pool_width = 8
  , tolerance = [0, 0, 0, 0, 1]
  , sitevs = [ids.objv_54]
  }

let pver_2 = types.Obj.Pver
  { id = ids.pver_2
  , data_units = 1
  , parity_units = 0
  , spare_units = 0
  , pool_width = 1
  , tolerance = [0, 0, 0, 1, 0]
  , sitevs = [ids.objv_76]
  }

let pool_48 = types.Obj.Pool
  { id = ids.pool_48
  , pvers = [ids.pver_f, ids.pver_49]
  }

let pool_69 = types.Obj.Pool
  { id = ids.pool_69
  , pvers = [ids.pver_2]
  }

let pool_1 = types.Obj.Pool
  { id = ids.pool_1
  , pvers = [ids.pver_63]
  }

let service_41 = types.Obj.Service
  { id = ids.service_41
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_40
  , sdevs = [] : List types.Oid
  }

let service_43 = types.Obj.Service
  { id = ids.service_43
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_42
  , sdevs = [] : List types.Oid
  }

let service_39 = types.Obj.Service
  { id = ids.service_39
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_38
  , sdevs = [] : List types.Oid
  }

let service_28 = types.Obj.Service
  { id = ids.service_28
  , type = types.SvcT.M0_CST_CONFD
  , endpoint = endpoints.process_27
  , sdevs = [] : List types.Oid
  }

let service_29 = types.Obj.Service
  { id = ids.service_29
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_27
  , sdevs = [] : List types.Oid
  }

let service_32 = types.Obj.Service
  { id = ids.service_32
  , type = types.SvcT.M0_CST_IOS
  , endpoint = endpoints.process_30
  , sdevs = [ ids.sdev_10, ids.sdev_22, ids.sdev_16, ids.sdev_8, ids.sdev_14
            , ids.sdev_18, ids.sdev_12, ids.sdev_20 ]
  }

let service_34 = types.Obj.Service
  { id = ids.service_34
  , type = types.SvcT.M0_CST_SNS_REB
  , endpoint = endpoints.process_30
  , sdevs = [] : List types.Oid
  }

let service_37 = types.Obj.Service
  { id = ids.service_37
  , type = types.SvcT.M0_CST_ISCS
  , endpoint = endpoints.process_30
  , sdevs = [] : List types.Oid
  }

let service_33 = types.Obj.Service
  { id = ids.service_33
  , type = types.SvcT.M0_CST_SNS_REP
  , endpoint = endpoints.process_30
  , sdevs = [] : List types.Oid
  }

let service_35 = types.Obj.Service
  { id = ids.service_35
  , type = types.SvcT.M0_CST_ADDB2
  , endpoint = endpoints.process_30
  , sdevs = [] : List types.Oid
  }

let service_36 = types.Obj.Service
  { id = ids.service_36
  , type = types.SvcT.M0_CST_CAS
  , endpoint = endpoints.process_30
  , sdevs = [ids.sdev_70]
  }

let service_31 = types.Obj.Service
  { id = ids.service_31
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_30
  , sdevs = [] : List types.Oid
  }

let service_45 = types.Obj.Service
  { id = ids.service_45
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_44
  , sdevs = [] : List types.Oid
  }

let service_47 = types.Obj.Service
  { id = ids.service_47
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_46
  , sdevs = [] : List types.Oid
  }

let service_25 = types.Obj.Service
  { id = ids.service_25
  , type = types.SvcT.M0_CST_HA
  , endpoint = endpoints.process_24
  , sdevs = [] : List types.Oid
  }

let service_26 = types.Obj.Service
  { id = ids.service_26
  , type = types.SvcT.M0_CST_RMS
  , endpoint = endpoints.process_24
  , sdevs = [] : List types.Oid
  }

let controller = types.Obj.Controller
  { id = ids.controller
  , drives = [ ids.drive_17, ids.drive_19, ids.drive_21, ids.drive_71
             , ids.drive_23, ids.drive_9, ids.drive_11, ids.drive_13
             , ids.drive_15 ]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let enclosure = types.Obj.Enclosure
  { id = ids.enclosure
  , node = ids.node
  , ctrls = [ids.controller]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let rack = types.Obj.Rack
  { id = ids.rack
  , encls = [ids.enclosure]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let site = types.Obj.Site
  { id = ids.site
  , racks = [ids.rack]
  , pvers = [ids.pver_2, ids.pver_49, ids.pver_63]
  }

let pver_f = types.Obj.PverF
  { id = ids.pver_f
  , cuid = 0
  , base = ids.pver_49
  , allowance = [0, 0, 0, 0, 1]
  }

let profile_77 = types.Obj.Profile
  { id = ids.profile
  , pools = [ids.pool_69, ids.pool_48, ids.pool_1]
  }

let objs =
  [ root
  , node
  , process_24
  , process_27
  , process_30
  , process_38
  , process_40
  , process_42
  , process_44
  , process_46
  , service_25
  , service_26
  , service_28
  , service_29
  , service_31
  , service_32
  , service_33
  , service_34
  , service_35
  , service_36
  , service_37
  , service_39
  , service_41
  , service_43
  , service_45
  , service_47
  , sdev_8
  , sdev_10
  , sdev_12
  , sdev_14
  , sdev_16
  , sdev_18
  , sdev_20
  , sdev_22
  , sdev_70
  , site
  , rack
  , enclosure
  , controller
  , drive_9
  , drive_11
  , drive_13
  , drive_15
  , drive_17
  , drive_19
  , drive_21
  , drive_23
  , drive_71
  , pool_1
  , pool_48
  , pool_69
  , pver_2
  , pver_49
  , pver_63
  , pver_f
  , objv_50
  , objv_51
  , objv_52
  , objv_53
  , objv_54
  , objv_55
  , objv_56
  , objv_57
  , objv_58
  , objv_59
  , objv_60
  , objv_61
  , objv_64
  , objv_65
  , objv_66
  , objv_67
  , objv_68
  , objv_72
  , objv_73
  , objv_74
  , objv_75
  , objv_76
  , profile_77
  ]

in toConfGen objs
