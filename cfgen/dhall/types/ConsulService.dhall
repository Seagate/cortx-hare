let Oid = ./Oid.dhall

in
{ node : Oid
, process : Oid
, service : ./SvcT.dhall
}
