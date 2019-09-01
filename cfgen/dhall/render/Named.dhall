let renderNamed
  = \(a : Type)
 -> \(f : a -> Text)
 -> \(name : Text)
 -> \(x : a)
 ->
    "${name}=${f x}"

-- -- XXX-UNCOMMENTME dhall 1.25.0 doesn't support equivalence operator (≡) yet.
-- -- https://github.com/dhall-lang/dhall-lang/tree/master/standard#equivalence
--
-- let example =
--     assert : renderNamed Natural Natural/show "answer" 42 ≡ "answer=42"

in renderNamed
