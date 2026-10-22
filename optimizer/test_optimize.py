"""Tests for optimize.py: run with  python test_optimize.py

Every optimization runs on every program; the 3AC machine executes the code before and
after and must print the same and leave the same values in main's variables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blocks import PROGRAM_DIRS, flow_graph, load  # noqa: E402
import optimize as o  # noqa: E402

NAMES = sorted({p.stem for d in PROGRAM_DIRS for p in d.glob("*.tac")})


def body(code):
    return [l.instr for l in code.lines]


def test_every_optimization_keeps_the_behaviour():
    for n in NAMES:
        for opt in o.ALL:
            r = opt(load(n))
            assert o.check(r), (n, opt.__name__)


def test_all_passes_one_after_another():
    """All optimizations in a row, until nothing changes."""
    for n in NAMES:
        code = load(n)
        steps = o.pipeline(code, o.ALL)
        final = steps[-1].after if steps else code
        assert code.run() == final.run(), n
        assert len(final.lines) <= len(code.lines) or n in ("verzweigung", "fakultaet", "summe"), n


def test_local_on_ausdruck():
    """x = 10 + 2 * 3 becomes x := 16."""
    steps = o.pipeline(load("ausdruck"))
    assert body(steps[-1].after) == ["x := 16"]
    assert [s.name for s in steps] == ["constant folding", "constant propagation", "constant folding",
                                       "dead code elimination", "constant propagation", "dead code elimination"]


def test_common_subexpressions_gemeinsam():
    r = o.common_subexpressions(load("gemeinsam"))
    assert [(c.line, c.before, c.after) for c in r.log] == [(5, "t4 := x * 2", "t4 := t3")]
    nodes = o.dag(load("gemeinsam"), "B1")
    star = [k for k, nd in enumerate(nodes) if nd["label"] == "*" and nd["names"] == ["t3", "t4"]]
    assert len(star) == 1                               # one node for x * 2, two names
    assert len(nodes) == 8


def test_single_local_rules():
    assert body(o.constant_folding(load("ausdruck")).after)[0] == "t1 := 6"
    r = o.strength_reduction(load("gemeinsam"))
    assert [c.after for c in r.log] == ["t3 := x + x", "t4 := x + x"]
    r = o.copy_propagation(load("sortieren"))
    assert [(c.line, c.after) for c in r.log] == [(38, "a[t21] := t15")]
    r = o.algebraic_simplification(load("sortieren"))
    assert [c.rule for c in r.log] == ["4 * 0 = 0", "4 * 1 = 4", "4 * 0 = 0"]
    r = o.common_subexpressions(load("sortieren"))
    assert [(c.line, c.after) for c in r.log] == [(31, "t16 := t14"), (36, "t20 := t17"), (37, "t21 := t18")]


def test_inline_expansion():
    r = o.inline_expansion(load("summe"))
    assert "sum" not in r.after.frames and r.after.run() == (["5050"], {})
    assert not any("call" in i for i in body(r.after))
    r = o.inline_expansion(load("fakultaet"))
    assert not r.log                                    # recursive: stays a call


def test_loop_optimizations_sortieren():
    r = o.loop_invariant_code_motion(load("sortieren"))
    assert [(c.line, c.before) for c in r.log] == [(17, "t7 := n - 1"), (18, "t8 := t7 - i"),
                                                   (13, "t6 := n - 1"), (17, "t7 := n - 1")]
    assert body(r.after)[11:15] == ["i := 0", "t6 := n - 1", "t7 := n - 1", "if i < t6 goto L2"]
    r = o.induction_variables(load("sortieren"))
    assert [c.after for c in r.log] == ["t9 := t28", "t14 := t28", "t16 := t28", "t28 := t28 + 4", "t28 := 4 * j"]
    assert len(r.after.lines) == 52


def test_unrolling_entfalten():
    r = o.loop_unrolling(load("entfalten"))
    assert "3 passes" in r.log[0].rule and flow_graph(r.after).loops() == []
    final = o.pipeline(r.after)[-1].after
    assert body(final) == ["s := 5", "i := 3", "print 5"]


def test_dead_code_debug():
    steps = o.pipeline(load("debug"))
    removed = [c.before for s in steps for c in s.log if s.name == "dead code elimination"]
    assert "print x" in removed
    assert body(steps[-1].after) == ["debug := 0", "x := 16", "goto L2", "t3 := x + x", "y := t3"]


def test_code_hoisting_heben():
    r = o.code_hoisting(load("heben"))
    assert [(c.line, c.after) for c in r.log] == [(5, "t1 := t6"), (9, "t3 := t6"), (None, "t6 := a * b")]
    assert body(r.after)[2:4] == ["t6 := a * b", "if a < b goto L1"]



def test_code_hoisting_keeps_the_block_label():
    """The branching block is only `price: if n > 10 goto L1`: the hoisted instruction must
    carry the label `price` (else it would sit behind `goto main` and never run)."""
    from blocks import Code, tac
    src = (Path(__file__).resolve().parent / "programs" / "preis.calc").read_text()
    out, rc = tac.run_calculator(src, "-s", "-t")
    assert rc == 0
    r = o.code_hoisting(Code.parse(out))
    assert [c.after for c in r.log] == ["t1 := t6", "t3 := t6", "t6 := n * c"]
    assert r.after.lines[1].labels == ["price"] and r.after.lines[1].instr == "t6 := n * c"
    assert r.after.lines[2].labels == [] and r.after.lines[2].instr == "if n > 10 goto L1"
    assert o.check(r) and r.after.run()[0] == ["31", "12"]
    steps = []
    tac.run(r.after.text(), steps)
    assert sum(s["instruction"] == "t6 := n * c" for s in steps) == 2      # runs once per call


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
