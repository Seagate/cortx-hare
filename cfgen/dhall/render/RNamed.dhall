let id = \(a : Type) -> \(x : a) -> x

let types = ../types.dhall

let named = ./Named.dhall
let namedList = ./NamedList.dhall
let renderOid = ./Oid.dhall

in
{ Natural = named Natural Natural/show
, Naturals = namedList Natural Natural/show
, Oid = named types.Oid renderOid
, Oids = namedList types.Oid renderOid
, Text = named Text Text/show
, Texts = namedList Text Text/show
, TextUnquoted = named Text (id Text)
}
