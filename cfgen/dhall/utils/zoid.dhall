{- Create an `Oid` value with zeroed `cont7` field. -}

let types = ../types.dhall

in
    \(objt : types.ObjT)
 -> \(key : Natural)
 ->
    { cont7 = 0 } /\ { type = objt, key = key } : types.Oid
