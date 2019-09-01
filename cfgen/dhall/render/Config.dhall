let Prelude = ../Prelude.dhall

let types = ../types.dhall

let renderObj = ./Obj.dhall

in
\(objs : List types.Obj) ->
    let rendered = Prelude.List.map types.Obj Text renderObj objs
    in
    Prelude.Text.concatSep "\n" rendered ++ "\n"
