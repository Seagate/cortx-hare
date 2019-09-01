let Oid = ./Oid.dhall

in
-- m0_confx_node
{ id : Oid
, nr_cpu : Natural
, memsize_MB : Natural
, processes : List Oid
}
