let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall
let renderOid = ./Oid.dhall

in
\(x : types.Process) ->
    let memsize_KiB = x.memsize_MB * 1024
    in
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Naturals "cores" (Prelude.List.replicate x.nr_cpu Natural 1)
      , "mem_limit_as=134217728"  -- = BE_SEGMENT_SIZE = 128MiB
      , named.Natural "mem_limit_rss" memsize_KiB
      , named.Natural "mem_limit_stack" memsize_KiB
      , named.Natural "mem_limit_memlock" memsize_KiB
      , named.Text "endpoint" (./Endpoint.dhall x.endpoint)
      , named.Oids "services" x.services
      ]
 ++ ")"
