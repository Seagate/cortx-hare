let types = ../types.dhall

in
\(x : types.Endpoint) ->
    let nat = Natural/show
    in "${./NetId.dhall x.nid}:12345:${nat x.portal}:${nat x.tmid}"
