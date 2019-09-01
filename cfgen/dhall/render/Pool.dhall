let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Pool) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , "pver_policy=0"
      , named.Oids "pvers" x.pvers
      ]
 ++ ")"
