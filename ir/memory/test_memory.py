"""Tests for episode 29. Run: python test_memory.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from addresses import calculator, record, regions  # noqa: E402
from heap import COUNTER, MORE, STEPS, simulate  # noqa: E402


def test_heap_first_fit():
    p = simulate("first fit", STEPS + MORE)
    assert p[5][2] == "...bbbb..ddddd.."            # after free a, free c: 7 cells free
    assert p[6][1] == 0 and p[7][1] is None          # e at the front, f fits nowhere
    assert p[7][2].count(".") == 7 - 2               # yet 5 cells are free
    assert p[8][2] == "ee.......ddddd.." and p[9][1] == 2   # free b merges, f fits


def test_heap_best_fit():
    p = simulate("best fit", STEPS)
    assert p[6][1] == 7 and p[7][1] == 0             # e into the hole of two, f at the front


def test_heap_counterexample():
    # best fit is not always better: tiny leftovers, and g fails where first fit finds room
    first = simulate("first fit", COUNTER)
    best = simulate("best fit", COUNTER)
    assert first[5][2] == best[5][2] == ".....bb....ddddd"     # holes of 5 and 4
    assert best[7][2] == "ffff.bbeee.ddddd" and best[8][1] is None
    assert best[8][2].count(".") == 2                          # two single cells free
    assert first[8][2] == "eeeggbbffffddddd" and first[8][1] == 3


def test_regions():
    for run in regions():
        code = run[0]["visit"]
        for a in run:
            assert code < a["total"] < a["calls"] < a["*box"] < a["here"]   # code, static, heap, stack
            assert a["calls"] - a["total"] == 4                           # static local next to the global
        assert run[1]["here"] < run[0]["here"] and run[2]["here"] < run[1]["here"]   # the stack grows down
        assert run[0]["*box"] < run[1]["*box"] < run[2]["*box"]                     # the heap grows up here


def test_calculator_heap():
    # fact(5): five tables; fact(4) (y = fact(x / 4)): the first one lands where fact(5)
    # freed memory, the others in a completely different piece of heap (more than 1 GB away).
    _, err = calculator()
    lines = [z.split() for z in err.splitlines() if z.startswith("frame fact heap")]
    tables = [int(z[3], 16) for z in lines]
    stack = max(int(z[7], 16) for z in lines)
    assert len(tables) == 9
    five, four = tables[:5], tables[5:]
    assert five[0] <= four[0] < five[-1] + 1208
    assert all(abs(a - five[0]) > 10**9 for a in four[1:])
    assert all(a > stack for a in four[1:])           # even above the stack


def test_record():
    out = record()
    assert "entry: type 0, num 8, has_value 16, size 24" in out
    assert "entry_sorted: num 0, type 8, has_value 9, size 16" in out
    assert "vars[2] at +48" in out


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
