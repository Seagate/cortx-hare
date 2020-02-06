let types = ../types.dhall

in
    \(proto : types.Protocol)
 -> \(ipaddr : Text)
 -> \(portal : Natural)
 -> \(tmid : Natural)
 ->
    let addr = { ipaddr = ipaddr, mdigit = None Natural }
    in
      { nid = merge { tcp = types.NetId.tcp { tcp = addr }
                    , o2ib = types.NetId.o2ib { o2ib = addr }
                    } proto
      , portal = portal
      , tmid = tmid
      } : types.Endpoint
