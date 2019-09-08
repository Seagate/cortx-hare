let types = ../types.dhall

in
\(x : types.SdevMediaT) ->
    merge
    { DISK = "1"
    , SSD  = "2"
    , TAPE = "3"
    , ROM  = "4"
    }
    x
