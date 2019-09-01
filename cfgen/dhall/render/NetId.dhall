let types = ../types.dhall

let renderAddr = \(label : Text) -> \(addr : types.Addr)
 ->
    let mdigit = Optional/fold Natural addr.mdigit Text Natural/show ""
    in "${addr.ipaddr}@${label}${mdigit}"

in
\(nid : types.NetId) ->
    merge
    { lo = "0@lo"
    , tcp = \(x : { tcp : types.Addr }) -> renderAddr "tcp" x.tcp
    , ib = \(x : { ib : types.Addr }) -> renderAddr "o2ib" x.ib
    }
    nid
