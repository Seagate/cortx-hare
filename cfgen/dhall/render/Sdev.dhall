let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Sdev) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.Natural "dev_idx" x.dev_idx
      , named.Natural "iface" x.iface
      , named.Natural "media" x.media
      , named.Natural "bsize" x.bsize
      , named.Natural "size" x.size
      , "last_state=0"
      , "flags=0"
      , named.Text "filename" x.filename
      ]
 ++ ")"
