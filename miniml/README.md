# miniml: a tiny functional language (episodes 37–40)

Mini-ML is a small version of ML: everything is an expression, functions are values, `let` names
a value once and for all, `let val rec` defines recursive functions. Pure Python 3, no
dependencies.

| File | What it does |
|---|---|
| `miniml.py` | Episode 37: lexer, parser, abstract syntax and a pretty printer |
| `type_inference.py` | Episode 38: type inference step by step: a type variable for every node, one equation per use, unification, let-polymorphism |
| `interpreter.py` | Episode 39: an interpreter with environments and closures (call by value, static binding) |
| `secd.py` | Episode 40: compiling Mini-ML to SECD code, and the SECD machine with its four registers S, E, C, D |

## Try it

```bash
python miniml.py "let val x = 10 + 2 * 3 in x end"
python type_inference.py "fn f => fn x => f (f x)"
python interpreter.py "(fn i => i * 2) z" z=7
python secd.py "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact 3 end"
```

Tests: `python test_miniml.py`, `python test_type_inference.py`, `python test_evaluation.py`
(the interpreter and the SECD machine compute the same values).
