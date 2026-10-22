"""Tests for peephole.py (and the pipeline of all phases, where present).

Usage: python test_peephole.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import codegen  # noqa: E402
import peephole  # noqa: E402
import tac  # noqa: E402

TAC_PROGRAMS = codegen.TAC_DIR / "programs"
PROGRAMS = sorted(TAC_PROGRAMS.glob("*.tac"))
EMPTY = tac.read_program("# frame main, depth 0, size 8\n#   x int var 4 0\n#   y int var 4 4\n")


def rules(asm):
    new, log = peephole.optimize(asm)
    return new, [c.rule for c in log]


def test_semantics_all_programs():
    for path in PROGRAMS:
        text = path.read_text()
        for n, naive in ((2, False), (3, False), (2, True)):
            r = codegen.generate(text, n, naive=naive)
            new, log = peephole.optimize(r.asm)
            before, after = peephole.check(r.asm, new, r.program, n)
            assert len([l for l in new if not l.endswith(":")]) <= len([l for l in r.asm if not l.endswith(":")])
            assert after.steps <= before.steps, path.name
            assert after.output == tac.run(text).output


def test_single_rules():
    assert rules(["ST R0, x", "LD R0, x", "ST R0, y"]) == (["ST R0, x", "ST R0, y"], ["redundant load"])
    assert rules(["LD R0, x", "ST R0, x", "PRINT R0"])[1] == ["redundant store"]
    assert rules(["JMP L1", "L1:", "PRINT #1"]) == (["PRINT #1"], ["jump to next line", "unused label"])
    new, r = rules(["LD R0, #1", "CMP R0, #2", "JLT L1", "PRINT #0", "L1:", "JMP L2", "PRINT #9", "L2:", "PRINT #1"])
    assert "jump to jump" in r and "JLT L2" in new and "unreachable code" in r
    assert rules(["LD R0, x", "ADD R0, #0", "ST R0, y"])[1] == ["algebraic identity"]
    assert rules(["LD R0, x", "MUL R0, #8", "ST R0, y"])[0][1] == "SHL R0, #3"
    assert rules(["LD R0, x", "ADD R0, #1", "ST R0, x"])[0][1] == "INC R0"
    new, r = rules(["JLE L1", "JMP L2", "L1:", "PRINT #1", "L2:"])
    assert new[0] == "JGT L2" and r[0] == "jump over jump"
    # store a constant directly only if the register is not read afterwards
    assert rules(["LD R0, #16", "ST R0, x"])[0] == ["MOV #16, x"]
    assert rules(["LD R0, #16", "ST R0, x", "ADD R0, y", "ST R0, y"])[1] == []
    assert rules(["LD R0, #16", "ST R0, x", "LD R0, y", "PRINT R0"])[0][0] == "MOV #16, x"
    for asm in (["LD R0, #16", "ST R0, x"], ["LD R1, #5", "ST R1, x", "LD R0, x", "MUL R0, #8", "ST R0, y"]):
        _, m = peephole.check(asm, peephole.optimize(asm)[0], EMPTY, 2)
    assert m.globals() == {"x": 5, "y": 40}


def test_log():
    text = (TAC_PROGRAMS / "summe.tac").read_text()
    r = codegen.generate(text, 2)
    new, log = peephole.optimize(r.asm)
    assert [c.rule for c in log] == ["jump over jump", "unused label", "special instruction"]
    assert log[0].before == ["JLE L2", "JMP L3", "L2:"] and log[0].after == ["JGT L3", "L2:"]
    assert log[0].position == 9


def test_all_phases():
    try:
        import pipeline
    except ImportError:             # pipeline.py is not part of every copy of this folder
        return
    phases = dict(pipeline.stages("x = 10 + 2 * 3", 2))
    assert phases["tokens"] == "IDENT[x] ASSIGN NUMBER[10] PLUS NUMBER[2] TIMES NUMBER[3] NEWLINE"
    tac_text = phases["three-address code"]
    assert [l.strip() for l in tac_text.splitlines() if not l.startswith("#")] == \
        ["t1 := 2 * 3", "t2 := 10 + t1", "x := t2"]
    opt = next(v for k, v in phases.items() if k.startswith("optimized"))
    assert opt.splitlines()[-1].strip() == "x := 16"
    assert phases["assembler (unoptimized 3AC), 2 registers"].split("\n") == \
        ["    LD R0, #2", "    MUL R0, #3", "    LD R1, #10", "    ADD R1, R0", "    ST R1, x"]
    assert phases["assembler, 2 registers"] == "    LD R0, #16\n    ST R0, x"
    assert phases["peephole"].endswith("    MOV #16, x")            # as in episode 1
    assert phases["run"].startswith("x = 16")


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
