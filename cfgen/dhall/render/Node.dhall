let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Node) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Natural "memsize" x.memsize_MB
      , named.Natural "nr_cpu" x.nr_cpu
      , named.Natural "last_state" 0
      , named.Natural "flags" 0
      , named.Oids "processes" x.processes
      ]
 ++ ")"
