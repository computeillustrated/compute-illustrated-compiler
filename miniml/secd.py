"""Compiling Mini-ML to SECD code, and the SECD machine.

Instructions:
    LD c        load constant            LDV n     load variable n of the environment (1 = first)
    LDC C'      load closure (C', E)     APP       apply closure to the argument below it
    DUM n       n placeholders Ω in E    RAP n     recursive apply: fill the placeholders
    COND(C1,C2) branch on true/false     RET       return from a branch
    ADD SUB MULT EQ LT NOT               primitives (second operand on top of the stack)

Translation (N = list of names, matches the environment at run time):
    c                               LD c
    x                               LDV position(x, N)
    if c then e1 else e2            c · COND(e1 · RET, e2 · RET)
    e1 op e2                        e1 · e2 · OP
    e e'                            e' · e · APP
    fn x => e                       LDC (e in x·N)
    let val x = e' in e end         e' · LDC (e in x·N) · APP
    let val rec x1 = e1 and ... and xn = en in e end
                                    DUM n · e1 · ... · en (all in N') · LDC (e in N') · RAP n
                                    with N' = [x1, ..., xn]·N

    code = compile_ml("let val rec fact = ... in fact 3 end")
    value, trace = run(code)

Trace: list of dicts, one per machine state, starting with ([], [], C, []):
    step   number of the state (0 = start)
    instr  instruction that led to this state (None for the start, "return" when C ran empty)
    S, E, C, D   each register as a list of item texts (top / first element first)
show_state(entry) gives the state as one line "(S, E, C, D)".

Usage:  python secd.py "let val rec fact = fn n => if n < 2 then 1 else n * fact (n - 1) in fact 3 end"
"""

import sys
from dataclasses import dataclass

from miniml import App, BinOp, Const, Fn, If, Let, LetRec, UnOp, Var, as_ast

ABBREV = {}               # code text -> short name, used when printing closures (see run)

OPCODES = {"+": "ADD", "-": "SUB", "*": "MULT", "=": "EQ", "<": "LT", "not": "NOT"}


# ---------------------------------------------------------------- compiler

def position(x, names):
    for i, n in enumerate(names, 1):
        if n == x:
            return i
    raise NameError(f"unbound name {x}")


def compile_ml(program, names=None):
    """Mini-ML -> SECD code (list of instruction tuples)."""
    return _compile(as_ast(program), list(names or []))


def _compile(e, N):
    if isinstance(e, Const):
        return [("LD", e.value)]
    if isinstance(e, Var):
        return [("LDV", position(e.name, N))]
    if isinstance(e, If):
        return _compile(e.cond, N) + [("COND", _compile(e.then, N) + [("RET",)],
                                               _compile(e.else_, N) + [("RET",)])]
    if isinstance(e, BinOp):
        return _compile(e.left, N) + _compile(e.right, N) + [(OPCODES[e.op],)]
    if isinstance(e, UnOp):
        return _compile(e.arg, N) + [(OPCODES[e.op],)]
    if isinstance(e, App):
        return _compile(e.arg, N) + _compile(e.fn, N) + [("APP",)]
    if isinstance(e, Fn):
        return [("LDC", _compile(e.body, [e.param] + N))]
    if isinstance(e, Let):
        return _compile(e.value, N) + [("LDC", _compile(e.body, [e.name] + N)), ("APP",)]
    if isinstance(e, LetRec):
        n = len(e.bindings)
        N2 = [name for name, _ in e.bindings] + N
        code = [("DUM", n)]
        for _, value in e.bindings:
            code += _compile(value, N2)
        return code + [("LDC", _compile(e.body, N2)), ("RAP", n)]
    raise TypeError(e)


def show_value(v, rec_names=None):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if v is OMEGA:
        return "Ω"
    if isinstance(v, Closure):
        code = show_code(v.code)
        return f"({ABBREV.get(code, code)}, {show_env(v.env, inside_closure=True)})"
    raise TypeError(v)


def show_instr(i):
    op = i[0]
    if op == "LD":
        return f"LD {show_value(i[1])}"
    if op == "LDC":
        return f"LDC {show_code(i[1])}"
    if op == "COND":
        return f"COND({show_code(i[1])}, {show_code(i[2])})"
    if len(i) == 2:
        return f"{op} {i[1]}"
    return op


def show_code(code):
    return "[" + ", ".join(show_instr(i) for i in code) + "]"


# ---------------------------------------------------------------- machine

class _Omega:
    pass


OMEGA = _Omega()


class RecEnv(list):
    """Environment created by DUM; closures refer to it, RAP fills its placeholders."""
    count = 0

    def __init__(self, items):
        super().__init__(items)
        RecEnv.count += 1
        self.label = f"E'{RecEnv.count}"


@dataclass(eq=False)
class Closure:
    code: list
    env: list


def show_env(env, inside_closure=False):
    if inside_closure and isinstance(env, RecEnv):
        return env.label
    return "[" + ", ".join(show_value(v) for v in env) + "]"


def _items(S, E, C, D):
    def dump_item(d):
        s, e, c = d
        return f"({'[' + ', '.join(show_value(v) for v in s) + ']'}, {show_env(e)}, {show_code(c)})"
    return {"S": [show_value(v) for v in S], "E": [show_value(v) for v in E],
            "C": [show_instr(i) for i in C], "D": [dump_item(d) for d in D],
            "E_label": E.label if isinstance(E, RecEnv) else None}


def run(code, max_steps=100000, abbrev=None):
    """Runs the machine from ([], [], code, []) until C and D are empty. Returns (value, trace).

    abbrev: {code text: short name}, e.g. {"[LDV 1, LD 1, ADD]": "C1"}; closures with that
    code are shown as (C1, E) in the trace."""
    ABBREV.clear()
    ABBREV.update(abbrev or {})
    RecEnv.count = 0
    S, E, C, D = [], [], list(code), []
    trace = [{"step": 0, "instr": None, **_items(S, E, C, D)}]
    while C or D:
        if len(trace) > max_steps:
            raise RuntimeError("too many steps")
        if not C:
            # end of a function body: restore the saved state, keep the result
            x = S[0]
            s, e, c = D[0]
            S, E, C, D = [x] + s, e, c, D[1:]
            instr = "return"
        else:
            i, C = C[0], C[1:]
            op = i[0]
            instr = show_instr(i)
            if op == "LD":
                S = [i[1]] + S
            elif op == "LDV":
                S = [E[i[1] - 1]] + S
            elif op == "LDC":
                S = [Closure(i[1], E)] + S
            elif op == "APP":
                clo, x, S = S[0], S[1], S[2:]
                D = [(S, E, C)] + D
                S, E, C = [], [x] + clo.env, list(clo.code)
            elif op == "DUM":
                E = RecEnv([OMEGA] * i[1] + E)
            elif op == "RAP":
                n = i[1]
                clo, defs, S = S[0], S[1:n + 1], S[n + 1:]
                rec = clo.env                     # the environment made by DUM
                for k, v in enumerate(reversed(defs)):
                    rec[k] = v                    # E'[1] := cl1, ..., E'[n] := cln
                D = [(S, E[n:], C)] + D
                S, E, C = [], rec, list(clo.code)
            elif op == "COND":
                b, S = S[0], S[1:]
                D = [([], [], C)] + D
                C = list(i[1] if b else i[2])
            elif op == "RET":
                _, _, c = D[0]
                C, D = c, D[1:]
            elif op == "NOT":
                S = [not S[0]] + S[1:]
            else:
                y, x, S = S[0], S[1], S[2:]
                r = {"ADD": x + y, "SUB": x - y, "MULT": x * y, "EQ": x == y, "LT": x < y}[op]
                S = [r] + S
        trace.append({"step": len(trace), "instr": instr, **_items(S, E, C, D)})
    return S[0], trace


def show_state(entry):
    reg = lambda xs: "[" + ", ".join(xs) + "]"
    return f"({reg(entry['S'])}, {reg(entry['E'])}, {reg(entry['C'])}, {reg(entry['D'])})"


def evaluate(program, abbrev=None):
    """Compile and run: value and trace."""
    return run(compile_ml(program), abbrev=abbrev)


if __name__ == "__main__":
    code = compile_ml(sys.argv[1])
    print(show_code(code))
    value, trace = run(code)
    for entry in trace:
        print(f"{entry['step']:3} {entry['instr'] or '':<12} {show_state(entry)}")
    print("value:", show_value(value))
