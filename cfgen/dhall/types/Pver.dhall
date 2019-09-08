let Oid = ./Oid.dhall

in
-- m0_confx_pver_actual
{ id : Oid
, data_units : Natural    -- N
, parity_units : Natural  -- K
, pool_width : Natural    -- P
, tolerance : List Natural
, sitevs : List Oid
}
