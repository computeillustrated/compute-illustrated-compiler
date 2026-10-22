# optimizer: optimization and code generation (episodes 41–47)

Python 3 tools that work on the calculator's real three-address code (`./run.sh -s -t`, files
`.tac`). Every transformation is checked by running the code before and after on the
three-address machine `tac.py` from `../ir/`, which these modules find on their own.

| File | What it does |
|---|---|
| `blocks.py` | Episode 41: leaders, basic blocks, the flow graph and its loops |
| `optimize.py` | Episodes 42–43: constant folding, copy propagation, common subexpressions, the DAG, inlining, loop-invariant code motion, induction variables, unrolling, dead code |
| `dataflow.py` | Episode 45: data-flow analysis on the flow graph: gen, kill, in, out for reaching definitions, available expressions, live variables and very busy expressions, round by round |
| `codegen.py` | Episodes 44 and 46: assembler for a simple target machine, with register and address descriptors, `getreg` and spilling; the machine runs the result |
| `peephole.py` | Episode 44: a small window slides over the assembler and removes what is not needed |
| `programs/` | Example programs (`.calc`) and their three-address code (`.tac`); `../ir/programs/` is searched too |

## Try it

```bash
python blocks.py sortieren
python optimize.py sortieren all
python dataflow.py sortieren live
python codegen.py ../ir/programs/ausdruck.tac 2 --log
python peephole.py ../ir/programs/ausdruck.tac
```

Tests: `python test_blocks.py`, `python test_optimize.py`, `python test_dataflow.py`,
`python test_codegen.py`, `python test_peephole.py`.

The example programs keep the (German) names they have in the videos: `doppelt` (duplicate),
`entfalten` (unroll), `heben` (hoist), `preis` (price), `debug`; the ones in `../ir/programs/` are
explained in `../ir/README.md`.
