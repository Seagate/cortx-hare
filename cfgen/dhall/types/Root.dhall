let Oid = ./Oid.dhall

in
-- m0_confx_root
{ id : Oid
, mdpool : Oid
, imeta_pver : Optional Oid
, nodes : List Oid
, sites : List Oid
, pools : List Oid
, profiles : List Oid
}
