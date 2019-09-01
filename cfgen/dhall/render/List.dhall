let Prelude = ../Prelude.dhall

in
    \(a : Type)
 -> \(f : a -> Text)
 -> \(xs : List a)
 ->
    let items = Prelude.Text.concatMapSep ", " a f xs
    in "[${items}]"
