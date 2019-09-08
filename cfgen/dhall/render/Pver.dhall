let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Pver) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Natural "N" x.data_units
      , named.Natural "K" x.parity_units
      , named.Natural "P" x.pool_width
      , named.Naturals "tolerance" x.tolerance
      , named.Oids "sitevs" x.sitevs
      ]
 ++ ")"
