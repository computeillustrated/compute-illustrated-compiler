"""Tests for codegen.py: the generated assembler computes the same as the 3AC interpreter.

Usage: python test_codegen.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import codegen  # noqa: E402
import tac  # noqa: E402  (codegen puts the folder of tac.py on the path)

TAC_PROGRAMS = codegen.TAC_DIR / "programs"
PROGRAMS = sorted(TAC_PROGRAMS.glob("*.tac"))


def same(text, registers, naive=False):
    r = codegen.generate(text, registers, naive=naive)
    m = codegen.run(r.asm, r.program, registers)
    t = tac.run(text)
    assert m.output == t.output, (m.output, t.output)
    assert m.globals() == t.global_values(), (m.globals(), t.global_values())
    return r, m


def test_all_programs():
    for path in PROGRAMS:
        text = path.read_text()
        for n in (1, 2, 3, 4):
            if n == 1 and "] :=" in text:
                try:
                    same(text, n)
                except ValueError as e:
                    assert "two registers" in str(e)
                    continue
                raise AssertionError("array store with one register")
            r, _ = same(text, n)
            used = {a.strip(",") for z in r.asm for a in z.replace("[", " ").replace("]", " ").split()
                       if a.startswith("R") and a[1:].strip(",").isdigit()}
            assert all(int(b[1:]) < n for b in used), (path.name, n, used)
        same(text, 2, naive=True)


def test_expression():
    text = (TAC_PROGRAMS / "ausdruck.tac").read_text()
    r, m = same(text, 2)
    assert r.asm == ["LD R0, #2", "MUL R0, #3", "LD R1, #10", "ADD R1, R0", "ST R1, x"]
    assert m.globals() == {"x": 16}
    steps = r.log
    assert [s.tac for s in steps] == ["t1 := 2 * 3", "t2 := 10 + t1", "x := t2"]
    assert steps[0].con == {"R0": ["t1"], "R1": []}
    assert steps[1].con == {"R0": [], "R1": ["t2"]}           # t1 dead: R0 free again
    assert steps[2].code == ["ST R1, x"]                      # copy without an instruction, stored at the end of the block
    assert "reuse R1" in steps[2].decisions[0]
    assert steps[2].pos == {"x": ["R1", "x"]}
    # with one register: 10 must be loaded after t1, R0 is taken -> t1 is spilled
    r1, _ = same(text, 1)
    assert "ST R0, t1" in r1.asm


def test_block_with_spilling():
    """A block with two registers in which getreg has to free a register."""
    block = ["a := 4", "b := 6", "c := a + b", "d := c * a", "e := d - b"]
    code, log = codegen.gen_block(block, 2, live_end={"e", "a"})
    decisions = [d for s in log for d in s.decisions]
    assert any("no free register" in d for d in decisions), decisions
    assert any(d.startswith("getreg") and "is free" in d for d in decisions)
    assert any("reuse" in d for d in decisions)
    # check the result with a tiny symbol table
    text = "# frame main, depth 0, size 24\n" + "".join(
        f"#   {v} int var 4 {4 * i}\n" for i, v in enumerate("abcde")) + "".join("    " + b + "\n" for b in block)
    p = tac.read_program(text)
    m = codegen.Machine(code, p, 2).run()
    assert m.glob["e"] == (4 + 6) * 4 - 6 and m.glob["a"] == 4
    assert "b" not in m.glob and "c" not in m.glob               # dead at the end: never stored


def test_liveness():
    text = (TAC_PROGRAMS / "summe.tac").read_text()
    p = tac.read_program(text)
    blocks = codegen.liveness(p, codegen.split_blocks(p))
    assert len(blocks) == 7
    body = next(b for b in blocks if "L2" in b.labels)
    assert body.live_out == {"i", "s", "n"}
    end = next(b for b in blocks if "L3" in b.labels)
    assert end.live_out == set()                                  # main has no variables
    r, m = same(text, 2)
    assert m.output == ["5050"]


def test_factorial_recursion():
    text = (TAC_PROGRAMS / "fakultaet.tac").read_text()
    r, m = same(text, 2)
    assert m.output == ["120"] and m.globals() == {"x": 16, "y": 24}
    assert "CALL fact, 1" in r.asm


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
