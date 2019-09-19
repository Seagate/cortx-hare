let renderNamedList
  = \(a : Type)
 -> \(f : a -> Text)
 -> \(name : Text)
 -> \(xs : List a)
 ->
    "${name}=" ++ ./List.dhall a f xs

let example =
    assert : renderNamedList Natural Natural/show "bits" [ 0, 1 ] ===
        "bits=[0, 1]"

in renderNamedList
