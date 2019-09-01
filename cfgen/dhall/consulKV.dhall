let Prelude = ./Prelude.dhall

let defaults = ./defaults.dhall

let types = ./types.dhall

let render = ./render.dhall

let svcToKV = \(svc : types.ConsulService) ->
    defaults.KeyValue // { key = render.ConsulService svc }

in  \(arg : { services : List types.ConsulService, fid_keygen : Natural })
 ->
  [ defaults.KeyValue // { key = "leader" }
  , { key = "epoch", value = types.Value.Natural 1 }
  , { key = "fid_keygen", value = types.Value.Natural arg.fid_keygen }
  ]
  # Prelude.List.map types.ConsulService types.KeyValue svcToKV arg.services
  : List types.KeyValue
