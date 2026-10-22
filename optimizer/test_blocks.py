"""Tests for blocks.py: run with  python test_blocks.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blocks import PROGRAM_DIRS, flow_graph, leaders, load, parse, tac  # noqa: E402

NAMES = sorted({p.stem for d in PROGRAM_DIRS for p in d.glob("*.tac")})


def test_round_trip():
    """Code.text() runs exactly like the original .tac."""
    for n in NAMES:
        path = next(d / f"{n}.tac" for d in PROGRAM_DIRS if (d / f"{n}.tac").exists())
        m = tac.run(path.read_text())
        assert load(n).run() == (m.output, m.global_values()), n


def test_own_programs_are_real_compiler_output():
    for calc in (PROGRAM_DIRS[0]).glob("*.calc"):
        out, code = tac.run_calculator(calc.read_text(), "-s", "-t")
        assert code == 0 and out == calc.with_suffix(".tac").read_text(), calc.name


def test_block_shape():
    """Labels only on the first instruction of a block, jumps only at its end."""
    for n in NAMES:
        fg = flow_graph(load(n))
        for b in fg.blocks:
            for i in b.indices():
                if i != b.start:
                    assert not fg.code.lines[i].labels, (n, b.name)
                if i != b.end - 1:
                    assert parse(fg.code.lines[i].instr)[0] not in ("goto", "if", "return"), (n, b.name)


def test_sortieren():
    c = load("sortieren")
    fg = flow_graph(c)
    assert len(c.lines) == 50 and len(fg.blocks) == 12 and len(fg.edges) == 14
    lead = leaders(c)
    assert lead[0] == ["first instruction of the program"]
    assert lead[12] == ["target of goto in line 44"]                       # L1 = B2
    assert lead[16] == ["target of goto in line 41"]                       # L4 = B5
    assert lead[14] == ["follows the if in line 14"]
    assert ("B10", "B5", "jump") in fg.edges and ("B9", "B10", "fall-through") in fg.edges
    assert fg.succ("B2") == ["B4", "B3"] and sorted(fg.pred("B2")) == ["B1", "B11"]
    inner, outer = fg.loops()
    assert inner.header == "B5" and inner.back_edges == [("B10", "B5")]
    assert inner.blocks == ["B5", "B7", "B8", "B9", "B10"] and inner.exits == ["B5"]
    assert outer.header == "B2" and outer.back_edges == [("B11", "B2")] and len(outer.blocks) == 9
    assert fg.entry == {"main": "B1"} and fg.exits == {"main": ["B12"]}
    assert fg.dominators("main")["B10"] == {"B1", "B2", "B4", "B5", "B7", "B10"}


def test_functions():
    fg = flow_graph(load("fakultaet"))
    assert len(fg.blocks) == 6 and fg.entry == {"main": "B1", "fact": "B2"}
    assert fg.exits["fact"] == ["B4", "B5"] and fg.exits["main"] == ["B6"]
    assert leaders(fg.code)[1] == ["first instruction of function fact (called in lines 7, 14, 18)",
                                   "follows the goto in line 1"]
    assert fg.loops() == []                                              # recursion is no loop here
    fg = flow_graph(load("summe"))
    (loop,) = fg.loops()
    assert loop.header == "B3" and loop.blocks == ["B3", "B5"] and fg.block("B3").proc == "sum"


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
