"""Tests for representations.py and stack_machine.py.

Usage:  python test_representations.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from representations import all_forms, ast, parse_tree  # noqa: E402
from stack_machine import Address, for_line  # noqa: E402
from tac import read_program, run_calculator  # noqa: E402

EXPRESSION = "x = 10 + 2 * 3"
COMMON = "y = x * 2 + x * 2 * 3"


def reductions_from_trace(text):
    """[(left, [right…])] of every reduction in a bison yydebug trace."""
    result, right = [], []
    for line in text.splitlines():
        if line.startswith("Reducing stack"):
            right = []
        elif m := re.match(r"\s+\$\d+ = (?:token|nterm) (\w+)", line):
            right.append(m[1])
        elif m := re.match(r"-> \$\$ = nterm (\w+)", line):
            result.append((m[1], right))
    return result


def test_reductions_like_bison():
    """The parser here builds the same tree as the real calculator: the same reductions in
    the same order (from the yydebug trace, without the reductions to program)."""
    for line in (EXPRESSION, COMMON, "z = (x - 1) / 2"):
        text, _ = run_calculator(line, debug=True)
        real = [r for r in reductions_from_trace(text) if r[0] != "program"]
        assert list(parse_tree(line).reductions()) == real, line


def test_three_address_like_calculator():
    """3AC from the AST = output of calc -t (the calculator counts temporaries across the program)."""
    text, status = run_calculator(EXPRESSION + "\n" + COMMON, "-t")
    assert status == 0
    expected = [str(c) for c in all_forms(EXPRESSION)["tac"]] + \
        [str(c) for c in all_forms(COMMON, first_temp=3)["tac"]]
    assert [z.strip() for z in text.splitlines()] == expected


def test_expression():
    r = all_forms(EXPRESSION)
    assert r["postfix"] == "x 10 2 3 * + =".split()       # like the yacc postfix translator
    assert [str(c) for c in r["tac"]] == ["t1 := 2 * 3", "t2 := 10 + t1", "x := t2"]
    assert r["tac"] == r["tac_dag"] and r["dag"].shared() == []
    assert r["node_count"] == {"parse_tree": 17, "ast": 7, "dag": 7}
    assert r["quadruples"] == [("*", "2", "3", "t1"), ("+", "10", "t1", "t2"), (":=", "t2", "", "x")]
    assert r["triples"] == [("*", "2", "3"), ("+", "10", "(0)"), (":=", "x", "(1)")]


def test_common_subexpression():
    r = all_forms(COMMON)
    assert list(r["ast"].lines()) == ["=", "  y", "  +", "    *", "      x", "      2",
                                      "    *", "      *", "        x", "        2", "      3"]
    d = r["dag"]
    assert list(d.lines()) == ["n0: y", "n1: x", "n2: 2", "n3: *(n1, n2)", "n4: 3",
                               "n5: *(n3, n4)", "n6: +(n3, n5)", "n7: =(n0, n6)"]
    assert d.shared() == [3] and sorted(d.parents(3)) == [5, 6]
    assert r["node_count"] == {"parse_tree": 25, "ast": 11, "dag": 8}
    assert r["postfix"] == "y x 2 * x 2 * 3 * + =".split()
    assert [str(c) for c in r["tac"]] == \
        ["t1 := x * 2", "t2 := x * 2", "t3 := t2 * 3", "t4 := t1 + t3", "y := t4"]
    assert [str(c) for c in r["tac_dag"]] == \
        ["t1 := x * 2", "t2 := t1 * 3", "t3 := t1 + t2", "y := t3"]
    assert r["quadruples"] == [("*", "x", "2", "t1"), ("*", "x", "2", "t2"), ("*", "t2", "3", "t3"),
                               ("+", "t1", "t3", "t4"), (":=", "t4", "", "y")]
    assert r["triples"] == [("*", "x", "2"), ("*", "x", "2"), ("*", "(1)", "3"),
                            ("+", "(0)", "(2)"), (":=", "y", "(3)")]
    order, triples = r["indirect_triples"]
    assert order == [0, 1, 2, 3, 4] and triples == r["triples"]


def test_parentheses_vanish_in_ast():
    a = ast(parse_tree("z = (x - 1) / 2"))
    assert list(a.lines()) == ["=", "  z", "  /", "    -", "      x", "      1", "    2"]


def test_stack_machine_expression():
    r = for_line(EXPRESSION)
    assert [f"{b} {a}" if a else b for b, a in r["code"]] == \
        ["lvar x", "const 10", "const 2", "const 3", "mul", "add", "store"]
    stacks = [s["stack"] for s in r["steps"]]
    assert stacks == [[], [Address("x")], [Address("x"), 10], [Address("x"), 10, 2],
                      [Address("x"), 10, 2, 3], [Address("x"), 10, 6], [Address("x"), 16], []]
    assert r["steps"][-1]["memory"] == {"x": 16}
    only = for_line(EXPRESSION, expression_only=True)      # 10 2 3 * + without the assignment
    assert only["postfix"] == "10 2 3 * +".split() and only["steps"][-1]["stack"] == [16]
    assert max(len(s["stack"]) for s in only["steps"]) == 3


def test_stack_machine_common():
    r = for_line(COMMON, {"x": 16})
    assert len(r["code"]) == 11 and r["steps"][-1]["memory"] == {"x": 16, "y": 128}
    assert max(len(s["stack"]) for s in r["steps"]) == 4


def test_same_computation_in_3ac():
    """The same line as 3AC on the 3AC machine, with temporaries instead of a stack."""
    from tac import run
    text, _ = run_calculator(EXPRESSION, "-s", "-t")
    steps = []
    m = run(text, steps)
    assert [s["instruction"] for s in steps] == [str(c) for c in all_forms(EXPRESSION)["tac"]]
    assert [s["written"] for s in steps] == [[(8, 6)], [(12, 16)], [(0, 16)]]
    assert m.global_values() == {"x": 16} and read_program(text).frames["main"].size == 16


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
    print("ok")
