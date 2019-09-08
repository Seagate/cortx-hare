let types = ../types.dhall

in
\(x : types.SdevIfaceT) ->
    merge
    { ATA   = "1"
    , SATA  = "2"
    , SCSI  = "3"
    , SATA2 = "4"
    , SCSI2 = "5"
    , SAS   = "6"
    , SAS2  = "7"
    }
    x
