"""Tests for dataflow.py: run with  python test_dataflow.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blocks import PROGRAM_DIRS, flow_graph, load  # noqa: E402
from dataflow import ANALYSES, dead_assignments, live_variables, reaching_definitions  # noqa: E402
import optimize  # noqa: E402

NAMES = sorted({p.stem for d in PROGRAM_DIRS for p in d.glob("*.tac")})


def test_fixed_point_solves_the_equations():
    """At the end every block satisfies its two equations, for every analysis and procedure;
    the sets change monotonically from round to round (grow for any, shrink for all)."""
    for n in NAMES:
        code = load(n)
        fg = flow_graph(code)
        for proc in fg.procs():
            for f in ANALYSES.values():
                a = f(code, proc)
                assert not a.rounds[-1]["changed"], (n, a.name)
                for b in a.blocks:
                    if a.direction == "forward":
                        srcs = [a.OUT[p] for p in fg.pred(b)] + ([a.boundary] if b == fg.entry[proc] else [])
                        inner = a.IN[b]
                        assert a.OUT[b] == a.gen[b] | (a.IN[b] - a.kill[b])
                    else:
                        srcs = [a.IN[s] for s in fg.succ(b)] or [a.boundary]
                        inner = a.OUT[b]
                        assert a.IN[b] == a.gen[b] | (a.OUT[b] - a.kill[b])
                    if not srcs:                                # unreachable block
                        expect = set() if a.meet == "any" else a.universe
                    else:
                        expect = set().union(*srcs) if a.meet == "any" else set.intersection(*map(set, srcs))
                    assert inner == expect, (n, a.name, b)
                for r0, r1 in zip(a.rounds[1:], a.rounds[2:]):
                    for b in a.blocks:
                        for s in ("in", "out"):
                            ok = r0[s][b] <= r1[s][b] if a.meet == "any" else r0[s][b] >= r1[s][b]
                            assert ok, (n, a.name, b)


def test_reaching_definitions_sortieren():
    a = reaching_definitions(load("sortieren"), variables_only=True)
    assert len(a.rounds) - 1 == 4                       # 3 rounds change something, the 4th not
    assert a.definitions == {11: "n", 12: "i", 16: "j", 30: "h", 40: "j", 43: "i"}
    assert a.gen["B1"] == {11, 12} and a.kill["B1"] == {43}
    assert a.gen["B10"] == {40} and a.kill["B10"] == {16}
    assert a.IN["B5"] == {11, 12, 16, 30, 40, 43}
    assert a.IN["B2"] == {11, 12, 16, 30, 40, 43} and a.OUT["B11"] == {11, 16, 30, 40, 43}


def test_live_variables_summe():
    a = live_variables(load("summe"), "sum")
    assert a.gen["B5"] == {"i", "s"} and a.kill["B5"] == {"i", "s", "t1", "t2"}
    assert a.IN["B3"] == {"i", "n", "s"} and a.IN["B2"] == {"n"} and a.OUT["B6"] == set()
    assert len(a.rounds) - 1 == 3


def test_available_and_very_busy_heben():
    code = load("heben")
    av = ANALYSES["available"](code)
    assert av.IN["B5"] == {"a * b"}                    # after the if/else: computed on both paths
    vb = ANALYSES["busy"](code)
    assert "a * b" in vb.OUT["B1"]


def test_dead_code_from_liveness():
    code = load("gemeinsam")
    assert dead_assignments(code) == []
    cse = optimize.common_subexpressions(code).after
    prop = optimize.copy_propagation(cse).after
    assert prop.lines[5].instr == "t5 := t3 * 3"
    assert dead_assignments(prop) == [(4, "t4")]       # t4 := t3 is read by nobody now
    # without the rule "main's variables are live at the end" x and y would be dead as well
    assert {v for _, v in dead_assignments(prop, at_exit=set())} == {"t4", "x", "y"}


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
