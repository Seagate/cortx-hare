let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Pver) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Natural "N" x.N
      , named.Natural "K" x.K
      , named.Natural "P" x.P
      , named.Naturals "tolerance" x.tolerance
      , named.Oids "sitevs" x.sitevs
      ]
 ++ ")"
