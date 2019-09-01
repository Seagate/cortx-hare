let Oid = ./Oid.dhall

in
-- m0_confx_service
{ id : Oid
, type : ./SvcT.dhall
, endpoint : ./Endpoint.dhall
, sdevs : List Oid
}
