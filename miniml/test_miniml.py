"""Tests for the Mini-ML parser and printer.  Run: python test_miniml.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from miniml import App, BinOp, Fn, LetRec, MLSyntaxError, nodes, parse, show, tree

PROGRAMS = [
    "x = 10 + 2 * 3",
    "fn x => x",
    "(fn x => x) (fn x => 1)",
    "(fn i => i * 2) z",
    "f g x + y",
    "fn f => fn x => f (f x)",
    "if x < 3 then x else x * 2",
    "let val c = 4 in c * c + c end",
    "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact 3 end",
    "let val rec even = fn n => if n = 0 then true else odd (n - 1) "
    "and odd = fn n => if n = 0 then false else even (n - 1) in even 10 end",
    "not (1 < 2)",
    "1 - 2 - 3",
    "1 - (2 - 3)",
    "f (if b then 1 else 2)",
    "(fn x => x) 1 + 2",
]

# the printer is canonical: parse(show(parse(p))) prints the same text
for p in PROGRAMS:
    s = show(parse(p))
    assert show(parse(s)) == s, (p, s)
    assert s == p, (p, s)

# application binds strongest and is left-associative
e = parse("f g x + y")
assert isinstance(e, BinOp) and isinstance(e.left, App) and isinstance(e.left.fn, App)

# fun is sugar for val rec with curried fn
e = parse("let fun add x y = x + y in add 1 2 end")
assert isinstance(e, LetRec) and isinstance(e.bindings[0][1], Fn)
assert show(e) == "let val rec add = fn x => fn y => x + y in add 1 2 end"

# tree and preorder numbering
assert tree("(fn x => x) (fn x => 1)") == ("@", [("fn x", [("x", [])]), ("fn x", [("1", [])])])
assert [show(n) for n in nodes("(fn x => x) 3")] == ["(fn x => x) 3", "fn x => x", "x", "3"]

for bad in ["let val rec x = 3 in x end", "fn => x", "1 +", "let val x = 1 in x"]:
    try:
        parse(bad)
    except MLSyntaxError:
        pass
    else:
        raise AssertionError(bad)

print("test_miniml: ok")
