let Prelude = ../Prelude.dhall

let types = ../types.dhall

in
\(objs : List types.Obj) ->
    Prelude.Text.concatMapSep "\n" types.Obj ./Obj.dhall objs ++ "\n"
