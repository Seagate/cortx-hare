let types = ../types.dhall

in
    \(ipaddr : Text)
 -> \(portal : Natural)
 -> \(tmid : Natural)
 ->
    let addr = { ipaddr = ipaddr, mdigit = None Natural }
    in
      { nid = types.NetId.ib { ib = addr }
      , portal = portal
      , tmid = tmid
      } : types.Endpoint
