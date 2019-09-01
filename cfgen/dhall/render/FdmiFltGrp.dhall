let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.FdmiFltGrp) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Natural "rec_type" x.rec_type
      , named.Oids "filters" x.filters
      ]
 ++ ")"
