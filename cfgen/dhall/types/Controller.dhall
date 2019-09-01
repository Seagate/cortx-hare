let Oid = ./Oid.dhall

in
-- m0_confx_controller
{ id : Oid
, node : Oid
, drives : List Oid
, pvers :  List Oid
}
