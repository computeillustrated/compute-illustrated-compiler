"""Interpreter and SECD machine compute the same values.  Run: python test_evaluation.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import interpreter
import secd
from type_inference import type_of

PROGRAMS = {
    "3 * (4 + 1)": 15,
    "(fn x => x + 1) (4 + 3)": 8,
    "(fn x => x + 1) 3": 4,
    "let val c = 4 in c * c + c end": 20,
    "let val suc = fn x => x + 1 in suc (suc 7) end": 9,
    "let val x = 3 in (let val x = x * x in x + x end) - x end": 15,
    "let val x = 1 in let val plusx = fn y => x + y in let val x = 2 in plusx 3 end end end": 4,
    "let val twice = fn f => fn x => f (f x) in twice (fn n => n * 3) 2 end": 18,
    "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact 3 end": 6,
    "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact 5 end": 120,
    "let fun fib n = if n < 2 then n else fib (n - 1) + fib (n - 2) in fib 10 end": 55,
    "let val rec even = fn n => if n = 0 then true else odd (n - 1) "
    "and odd = fn n => if n = 0 then false else even (n - 1) in even 7 end": False,
    "let fun add x y = x + y in add 1 (2 * 3) end": 7,
    "let val id = fn x => x in if id true then id 1 else 2 end": 1,
    "not (2 < 1)": True,
    "10 - 2 - 3": 5,
}

for program, expected in PROGRAMS.items():
    v1, _ = interpreter.evaluate(program)
    v2, trace = secd.evaluate(program)
    assert v1 == expected and type(v1) is type(expected), (program, v1)
    assert v2 == expected and type(v2) is type(expected), (program, v2)
    type_of(program)                       # every test program is well typed
    last = trace[-1]
    assert last["C"] == [] and last["D"] == [] and len(last["S"]) == 1

# interpreter: (fn i => i * 2) z in the environment [z -> 7]
v, protocol = interpreter.evaluate("(fn i => i * 2) z", {"z": 7})
assert v == 14
assert protocol[0] == {"event": "enter", "rule": "app", "node": 0, "expr": "(fn i => i * 2) z",
                       "env": [("z", "7")], "depth": 0}
body = [s for s in protocol if s["event"] == "enter" and s["expr"] == "i * 2"][0]
assert body["env"] == [("i", "7"), ("z", "7")]
assert [s["rule"] for s in protocol if s["event"] == "enter"] == ["app", "fn", "var", "prim", "var", "const"]
assert len(protocol) == 12

# SECD: successor of 3, state by state
code = secd.compile_ml("(fn x => x + 1) 3")
assert secd.show_code(code) == "[LD 3, LDC [LDV 1, LD 1, ADD], APP]"
v, trace = secd.run(code)
assert [secd.show_state(e) for e in trace] == [
    "([], [], [LD 3, LDC [LDV 1, LD 1, ADD], APP], [])",
    "([3], [], [LDC [LDV 1, LD 1, ADD], APP], [])",
    "([([LDV 1, LD 1, ADD], []), 3], [], [APP], [])",
    "([], [3], [LDV 1, LD 1, ADD], [([], [], [])])",
    "([3], [3], [LD 1, ADD], [([], [], [])])",
    "([1, 3], [3], [ADD], [([], [], [])])",
    "([4], [3], [], [([], [], [])])",
    "([4], [], [], [])",
]

# SECD: translation of twice and of a recursive let
assert secd.show_code(secd.compile_ml("fn f => fn x => f (f x)")) == \
    "[LDC [LDC [LDV 1, LDV 2, APP, LDV 2, APP]]]"
FACT = "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact 3 end"
assert secd.show_code(secd.compile_ml(FACT)) == (
    "[DUM 1, LDC [LDV 1, LD 2, LT, COND([LD 1, RET], "
    "[LDV 1, LDV 1, LD 1, SUB, LDV 2, APP, MULT, RET])], LDC [LD 3, LDV 1, APP], RAP 1]")
v, trace = secd.evaluate(FACT, abbrev={"[LDV 1, LD 2, LT, COND([LD 1, RET], "
                                       "[LDV 1, LDV 1, LD 1, SUB, LDV 2, APP, MULT, RET])]": "F"})
assert v == 6 and len(trace) == 42
assert [e["instr"] for e in trace].count("APP") == 3      # fact 3, fact 2, fact 1
assert max(len(e["D"]) for e in trace) == 7     # RAP + 3 x (APP + COND)
after_rap = trace[4]
assert after_rap["instr"] == "RAP 1" and after_rap["E"] == ["(F, E'1)"]

print("test_evaluation: ok")
