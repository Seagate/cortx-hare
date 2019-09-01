let Oid = ./Oid.dhall

in
-- m0_confx_pver_formulaic
{ id : Oid
, cuid : Natural  -- cluster-unique identifier of this formulaic pver
, base : Oid
, allowance : List Natural
}
