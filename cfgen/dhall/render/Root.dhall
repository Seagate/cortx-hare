let Prelude = ../Prelude.dhall

let types = ../types.dhall

let named = ./RNamed.dhall
let renderOid = ./Oid.dhall

in
\(x : types.Root) ->
    "("
 ++ Prelude.Text.concatSep " "
      [ renderOid x.id
      , named.Natural "verno" 1
      , named.Oid "rootfid" x.id
      , named.Oid "mdpool" x.mdpool
      , named.TextUnquoted "imeta_pver"
            (Optional/fold types.Oid x.imeta_pver Text renderOid "(0,0)")
      , named.Natural "mdredundancy" 1  -- XXX Is this value OK for EES?
                                        --     Check with @madhav.
      , "params=[]"
      , named.Oids "nodes" x.nodes
      , named.Oids "sites" x.sites
      , named.Oids "pools" x.pools
      , named.Oids "profiles" x.profiles
      , "fdmi_flt_grps=[]"
      ]
 ++ ")"
