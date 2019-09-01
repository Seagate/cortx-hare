let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall

in
\(x : types.Service) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ ./Oid.dhall x.id
      , named.TextUnquoted "type" ("@" ++ ./SvcT.dhall x.type)
      , named.Texts "endpoints" [./Endpoint.dhall x.endpoint]
      , "params=[]"
      , named.Oids "sdevs" x.sdevs
      ]
 ++ ")"
