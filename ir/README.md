# ir: memory, frames and intermediate code (episodes 29–36)

Python 3 tools behind the episodes on run-time memory and intermediate code. Nothing to install;
`tac.py` builds the calculator from the root folder with `yacc`, `lex` and `cc` when it needs it.

| File | What it does |
|---|---|
| `memory/` | Episode 29: real addresses of code, globals, locals and heap from a C program, and a tiny heap with first fit and best fit |
| `frames.py` | Episode 30: procedure frames with control link, access link and display, checked against a real Python run of `shop.py` |
| `representations.py` | Episode 31: one line in every intermediate form: syntax tree, AST, DAG, postfix, three-address code, quadruples, triples, indirect triples |
| `stack_machine.py` | Episode 32: an abstract stack machine that runs postfix code |
| `tac.py` | Episodes 33–36: a machine that runs the calculator's three-address code (`./run.sh -s -t`), with frames, `param`, `call` and `return` |
| `programs/` | Example programs (`.calc`) and the three-address code the calculator makes from them (`.tac`) |

## Try it

```bash
python representations.py "y = x * 2 + x * 2 * 3"
python stack_machine.py "x = 10 + 2 * 3"
python frames.py
python tac.py programs/fakultaet.tac --steps
python memory/heap.py
```

Each `test_*.py` checks a module against real runs: `python test_tac.py`.

## Names as in the videos

The example programs keep the (German) names they have in the videos, so you find the same file
you see on screen: `ausdruck` (expression), `deklarationen` (declarations), `fakultaet` (factorial),
`feld` (array), `gemeinsam` (common subexpression), `kurzschluss` (short circuit), `sortieren` (sort),
`summe` (sum), `tabellen` (tables), `teilen` (divide), `und` (and), `verschachtelt` (nested),
`verzweigung` (branch), `wenn` (if).

In episode 29 the C program is shown as `bereiche.c`; here it is `memory/regions.c`.
