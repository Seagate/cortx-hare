let renderNamed
  = \(a : Type)
 -> \(f : a -> Text)
 -> \(name : Text)
 -> \(x : a)
 ->
    "${name}=${f x}"

let example =
    assert : renderNamed Natural Natural/show "answer" 42 === "answer=42"

in renderNamed
