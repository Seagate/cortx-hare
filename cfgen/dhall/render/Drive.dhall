let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Drive) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Oid "dev" x.sdev
      , named.Oids "pvers" x.pvers
      ]
 ++ ")"
