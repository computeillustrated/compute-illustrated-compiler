"""Tests for the 3AC generator (calculator with -t, -s) and the 3AC machine (tac.py).

Usage:  python test_tac.py

Core: for every program in programs/ the 3AC must do the same as the calculator itself.
Compared are the outputs (print in 3AC = a bare expression in the calculator) and the final
values of all global variables (for that, the calculator gets one extra line per variable at
the end, the bare name, which prints its value).
"""
import re
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tac import TacError, run, g, read_program, run_calculator, CALCULATOR_DIR  # noqa: E402

PROGRAMS = sorted((HERE / "programs").glob("*.calc"))
ECHO = re.compile(r"^\w+(\[\d+\])? = ")


def tac_of(path):
    text, status = run_calculator(path.read_text(), "-s", "-t")
    assert status == 0, text
    return text


def test_tac_files_up_to_date():
    """The .tac files are exactly the calculator's output (otherwise regenerate them)."""
    for path in PROGRAMS:
        assert tac_of(path) == path.with_suffix(".tac").read_text(), f"{path.name}: .tac out of date"


def test_same_as_calculator():
    for path in PROGRAMS:
        source = path.read_text()
        m = run(tac_of(path))
        values = m.global_values()
        extra = []
        for name, value in values.items():
            extra += [f"{name}[{i}]" for i in range(len(value))] if isinstance(value, list) else [name]
        text, status = run_calculator(source.rstrip("\n") + "\n" + "\n".join(extra))
        assert status == 0 and "error" not in text, f"{path.name}: {text}"
        bare = [z for z in text.splitlines() if not ECHO.match(z)]
        expected = m.output + [g(x) for w in values.values() for x in (w if isinstance(w, list) else [w])]
        assert bare == expected, f"{path.name}: calculator {bare} != 3AC {expected}"


def run_program(name, steps=None):
    return run((HERE / "programs" / f"{name}.tac").read_text(), steps)


def test_known_values():
    assert run_program("ausdruck").global_values() == {"x": 16}
    m = run_program("fakultaet")
    assert m.output == ["120"] and m.global_values() == {"x": 16, "y": 24}
    assert run_program("summe").output == ["5050"]
    assert run_program("gemeinsam").global_values() == {"x": 16, "y": 128}
    assert run_program("verzweigung").output == ["7"] and run_program("verzweigung").global_values() == {"m": 16}
    m = run_program("deklarationen")
    assert m.global_values() == {"n": 3, "r": 1.5, "s": 3.0, "v": [0, 0, 0, 6, 0]} and m.output == ["7"]
    assert run_program("kurzschluss").output == ["0", "1", "0"]
    assert run_program("feld").global_values() == {"a": [0, 1, 4, 9], "i": 4, "s": 10}
    assert run_program("sortieren").global_values()["a"] == [1, 3, 5, 7, 9]


def test_expression_exactly():
    """x = 10 + 2 * 3: three instructions, no labels, no jump around functions."""
    p = read_program((HERE / "programs" / "ausdruck.tac").read_text())
    assert p.instructions == ["t1 := 2 * 3", "t2 := 10 + t1", "x := t2"] and p.labels == {}
    main = p.frames["main"]
    assert main.size == 16
    assert [(e.name, e.kind, e.offset) for e in main.entries.values()] == \
        [("x", "var", 0), ("t1", "temp", 8), ("t2", "temp", 12)]


def test_symbol_tables():
    p = read_program((HERE / "programs" / "deklarationen.tac").read_text())
    main = p.frames["main"].entries
    assert [(e.name, e.type, e.size, e.offset) for e in main.values() if e.kind == "var"] == \
        [("n", "int", 4, 0), ("r", "float", 4, 4), ("s", "float", 4, 8), ("v", "int", 24, 16)]
    assert main["v"].length == 5 and main["t1"].offset == 40 and p.frames["main"].size == 80
    p = read_program((HERE / "programs" / "summe.tac").read_text())
    total = p.frames["sum"]
    assert total.depth == 1 and total.size == 40
    assert [(e.name, e.kind, e.offset) for e in total.entries.values()] == \
        [("n", "param", 16), ("i", "var", 20), ("s", "var", 24), ("t1", "temp", 32), ("t2", "temp", 36)]
    fact = read_program((HERE / "programs" / "fakultaet.tac").read_text()).frames["fact"]
    assert [(e.name, e.offset) for e in fact.entries.values()] == [("n", 16), ("t1", 20), ("t2", 24), ("t3", 28)]
    assert fact.size == 32


def test_conversion():
    """int → float is an instruction of its own; without it the machine stops."""
    p = read_program((HERE / "programs" / "deklarationen.tac").read_text())
    assert "t2 := inttofloat t1" in p.instructions and "t4 := inttofloat n" in p.instructions
    without = "# frame main, depth 0, size 8\n#   r float var 4 0\n    r := 1\n"
    try:
        run(without)
        assert False, "int into float without inttofloat was accepted"
    except TacError:
        pass
    text, status = run_calculator("float r\nr = 2 + 0.5\n", "-t")
    assert status == 0 and text.split() == "t1 := inttofloat 2 t2 := t1 + 0.5 r := t2".split()


def test_semantic_errors():
    for source, message in [("int a\na = 2.5", "error: cannot assign float to int a"),
                            ("y = z + 1", "error: z is not declared"),
                            ("int a[3]\na = 1", "error: a is an array"),
                            ("t1 = 5", "error: t1 is reserved for temporaries and labels")]:
        text, status = run_calculator(source, "-t")
        assert status == 1 and message in text, (source, text)


def test_frames_factorial():
    """fact(5): up to five frames of fact above main, each with its own n."""
    steps = []
    run_program("fakultaet", steps)
    deepest = max(steps, key=lambda s: len(s["frames"]))
    frames = deepest["frames"]
    assert [r["function"] for r in frames] == ["main"] + ["fact"] * 5
    assert [r["base"] for r in frames] == [0, 32, 64, 96, 128, 160]
    n = [dict((name, w) for _, name, w in r["cells"])["n"] for r in frames[1:]]
    assert n == [5, 4, 3, 2, 1]
    second = dict((name, w) for _, name, w in frames[2]["cells"])
    assert second["saved depth"] == 1 and second["saved display"] == 32   # the frame before
    assert sum(1 for s in steps if "call fact" in s["instruction"]) == 5 + 4   # fact(5) and fact(4)
    # The calculator calls fact just as often (-c)
    text, _ = run_calculator((HERE / "programs" / "fakultaet.calc").read_text(), "-c")
    assert sum(1 for z in text.splitlines() if z.strip().startswith("call fact")) == 9


def test_short_circuit():
    """a < b or c < d: a < b is true, so c < d is never compared."""
    steps = []
    m = run_program("kurzschluss", steps)
    executed = [s["instruction"] for s in steps]
    p = m.p
    or_compare = [b for b in p.instructions if b.startswith("if c < d")][1]
    assert or_compare == "if c < d goto L5" and or_compare not in executed
    assert executed.count("if c < d goto L1") == 1          # with and, c < d is needed


def test_grammar_without_conflicts():
    folder = Path(tempfile.mkdtemp())
    for name in ("calc.y", "calc.l", "value.h", "tac.c"):
        shutil.copy(CALCULATOR_DIR / name, folder / name)
    result = subprocess.run(["yacc", "-d", "-v", "calc.y"], cwd=folder, capture_output=True, text=True)
    assert result.returncode == 0 and result.stderr == "" and "conflict" not in (folder / "y.output").read_text()


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
    print("ok")
