let Oid = ./Oid.dhall

in
-- m0_confx_pver_actual
{ id : Oid
, N : Natural
, K : Natural
, P : Natural
, tolerance : List Natural
, sitevs : List Oid
}
