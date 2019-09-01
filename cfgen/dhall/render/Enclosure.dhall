let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Enclosure) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Oids "ctrls" x.ctrls
      , named.Oids "pvers" x.pvers
      ]
 ++ ")"
