let types = ../types.dhall

let renderObjT = ./ObjT.dhall

in
\(x : types.Oid) ->
    let cont : Text =
        if Natural/isZero x.cont7
        then ""
        else "${Natural/show x.cont7}:"
    in
    "${renderObjT x.type}-${cont}${Natural/show x.key}"
