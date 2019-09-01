let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.PverF) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Natural "id" x.cuid
      , named.Oid "base" x.base
      , named.Naturals "allowance" x.allowance
      ]
 ++ ")"
