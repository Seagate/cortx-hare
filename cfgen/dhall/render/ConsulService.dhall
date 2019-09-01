let Prelude = ../Prelude.dhall

let types = ../types.dhall

in
    \(x : types.ConsulService)
 ->
    Prelude.Text.concatSep "/"
      [ "node"
      , Natural/show x.node.key
      , "service"
      , ./SvcT.dhall x.service
      , Natural/show x.process.key
      ]
