let Oid = ./Oid.dhall

in
-- m0_confx_site
{ id : Oid
, racks : List Oid
, pvers : List Oid
}
