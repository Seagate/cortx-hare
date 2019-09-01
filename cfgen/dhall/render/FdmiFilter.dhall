let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.FdmiFilter) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Oid "id" x.filter_id
      , named.Text "root" x.filter_root
      , named.Oid "node" x.node
      , named.Texts "endpoints" x.endpoints
      ]
 ++ ")"
