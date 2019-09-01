let Oid = ./Oid.dhall

in
-- m0_confx_fdmi_filter
{ id : Oid
, filter_id : Oid  -- XXX s/Oid/Fid/
, filter_root : Text
, node : Oid  -- XXX s/Oid/Fid/
, endpoints : List Text
}
