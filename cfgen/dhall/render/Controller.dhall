let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Controller) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Oid "node" x.node
      , named.Oids "drives" x.drives
      , named.Oids "pvers" x.pvers
      ]
 ++ ")"
