let Oid = ./Oid.dhall

in
-- m0_confx_fdmi_flt_grp
{ id : Oid
, rec_type : Natural
, filters : List Oid  -- XXX s/Oid/Fid/
}
