let Oid = ./Oid.dhall

in
-- m0_confx_process
{ id : Oid
, nr_cpu : Natural
, memsize_MB : Natural
, endpoint : ./Endpoint.dhall
, services : List Oid
}
