"""Tests for type inference.  Run: python test_type_inference.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from type_inference import MLTypeError, describe, infer, show_type, type_of

FACT = "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact end"

EXPECTED = {
    "fn x => x": "'a -> 'a",
    "(fn x => x) (fn x => 1)": "'a -> int",
    "(fn x => x) 3": "int",
    "fn x => 1": "'a -> int",
    "fn x => fn y => x": "'a -> 'b -> 'a",
    "(fn x => fn y => x) 2": "'a -> int",
    "fn f => fn x => f (f x)": "('a -> 'a) -> 'a -> 'a",
    "fn f => fn g => fn x => f (g x)": "('a -> 'b) -> ('c -> 'a) -> 'c -> 'b",
    "fn x => x + 1": "int -> int",
    "fn x => fn y => x < y": "int -> int -> bool",
    "fn b => if b then 1 else 0": "bool -> int",
    FACT: "int -> int",
    "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact 3 end": "int",
    "let fun twice f x = f (f x) in twice end": "('a -> 'a) -> 'a -> 'a",
    "let val c = 4 in c * c + c end": "int",
    # let-polymorphism: id is used at bool and at int
    "let val id = fn x => x in if id true then id 1 else 2 end": "int",
    "not true": "bool",
}

for program, expected in EXPECTED.items():
    got = type_of(program)
    assert got == expected, (program, got, expected)

assert type_of("fn x => x", greek=True) == "α -> α"
assert type_of("(fn i => i * 2) z", env={"z": "int"}) == "int"

# protocol of the main example
t, protocol = infer("(fn x => x) (fn x => 1)")
kinds = [s["kind"] for s in protocol]
assert kinds.count("fresh") == 7            # 5 nodes + 2 parameters
assert kinds.count("equation") == 5
assert kinds[-1] == "result"
assert len(protocol) == 20, len(protocol)
assert describe(protocol[-1]) == "type: 'a -> int"
for s in protocol:
    describe(s)
    describe(s, greek=True)

# type errors
ERRORS = {
    "fn x => x x": "occurs",
    "if 1 then 2 else 3": "mismatch",
    "1 + true": "mismatch",
    "fn f => if f true then f 1 else 0": "mismatch",   # parameters are not polymorphic
    "(fn id => if id true then id 1 else 2) (fn x => x)": "mismatch",
    "y": "unbound",
}
for program, reason in ERRORS.items():
    try:
        infer(program)
    except MLTypeError as err:
        assert err.reason == reason, (program, err.reason)
        assert err.protocol[-1]["kind"] == "error"
    else:
        raise AssertionError(program)

print("test_type_inference: ok")
