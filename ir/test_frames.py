"""Tests for frames.py. Usage: python test_frames.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from frames import run  # noqa: E402

STEPS, OUTPUT = run()
CALLS = [s for s in STEPS if s.kind == "call"]
READS = [s for s in STEPS if s.kind == "read"]


def frame(s):
    return s.stack[s.frame]


def test_output():
    assert OUTPUT.strip() == "24"


def test_call_order():
    assert [frame(s).short() for s in CALLS] == [
        "main()", "order(n = 2)", "add(k = 0)", "add(k = 1)", "add(k = 2)", "shipping()"]
    assert [frame(s).depth for s in CALLS] == [0, 1, 2, 2, 2, 1]


def test_control_and_access_links():
    top = CALLS[-1].stack
    assert [r.control for r in top] == [None, 0, 1, 2, 3, 4]      # always the caller
    assert [r.access for r in top] == [None, 0, 1, 1, 1, 0]       # the enclosing function


def test_display_on_call():
    assert [s.display for s in CALLS] == [
        [0], [0, 1], [0, 1, 2], [0, 1, 3], [0, 1, 4], [0, 5, 4]]
    assert [frame(s).saved for s in CALLS] == [None, None, None, 2, 3, 1]


def test_reads():
    reads = [(frame(s).num, s.name, s.value, s.relative, s.chain) for s in READS]
    assert reads == [
        (2, "n", 2, 1, [2, 1]), (2, "price", 10, 2, [2, 1, 0]),
        (3, "n", 2, 1, [3, 1]), (3, "price", 10, 2, [3, 1, 0]),
        (4, "n", 2, 1, [4, 1]),
        (5, "price", 10, 1, [5, 0]),
        (4, "n", 2, 1, [4, 1]),
    ]


def test_display_restored_after_shipping():
    # The last read of n comes after the return from shipping: D[1] points to order again.
    last = READS[-1]
    assert last.line == 11 and last.display[1] == 1
    assert all(r.name != "shipping" for r in last.stack)


def test_hidden():
    # main has an n = 1 of its own, but add always reads the n of order (2): the search
    # along the access links stops at the first frame that has n, which is order.
    for s in READS:
        if s.name == "n":
            assert s.value == 2 and s.chain[-1] == 1
            assert s.stack[0].name == "main" and s.stack[0].locals["n"] == 1


def test_returns():
    values = [(frame(s).short(), s.value) for s in STEPS if s.kind == "return"]
    assert values == [("shipping()", 2), ("add(k = 2)", 4), ("add(k = 1)", 14),
                      ("add(k = 0)", 24), ("order(n = 2)", 24), ("main()", None)]


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
