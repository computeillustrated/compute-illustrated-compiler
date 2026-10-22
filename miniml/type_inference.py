"""Type inference for Mini-ML, step by step.

Every node of the expression tree gets a fresh type variable, every edge yields an
equation between type variables, and unification solves the equations one at a time.
Let-bound names are polymorphic: before a let body is inspected, the pending equations
are solved and the type of the bound expression is generalized; every use of the name
then gets a fresh instance.

    infer("fn x => x")  ->  (type, protocol)
    show_type(type)                   'a -> 'a
    show_type(type, greek=True)       α -> α

Protocol: a list of dicts, each with "kind":
    fresh        node gets a type variable       node, var, what ("node" or the parameter name)
    instance     a let-bound name is instantiated node, name, scheme, type
    equation     equation from an edge          node, left, right, reason
    unify        one step of unification        left, right, case, binding, subst, depth
    generalize   let-bound name gets a scheme   node, name, type, scheme (quantified vars)
    error        unification failed             reason ("occurs", "mismatch", "unbound"), left, right
    result       final type                     type (variables renamed 'a, 'b, ...)
Types inside the protocol are type objects; describe(step) renders a step as text.

Usage:  python type_inference.py "fn f => fn x => f (f x)"
"""

import sys
from dataclasses import dataclass

from miniml import (App, BinOp, Const, Fn, If, Let, LetRec, UnOp, Var,
                    as_ast, numbering, show)


# ---------------------------------------------------------------- types

@dataclass(frozen=True)
class TVar:
    n: int


@dataclass(frozen=True)
class TCon:
    name: str              # 'int' or 'bool'


@dataclass(frozen=True)
class TFun:
    arg: object
    res: object


INT, BOOL = TCon("int"), TCon("bool")
GREEK = "αβγδεζηθικλμνξπρστυφχψω"


def var_name(n, greek=False):
    if greek:
        base = GREEK[n % len(GREEK)]
        return base + (str(n // len(GREEK)) if n >= len(GREEK) else "")
    base = chr(ord("a") + n % 26)
    return "'" + base + (str(n // 26) if n >= 26 else "")


def show_type(t, greek=False, arrow="->"):
    if isinstance(t, TVar):
        return var_name(t.n, greek)
    if isinstance(t, TCon):
        return t.name
    left = show_type(t.arg, greek, arrow)
    if isinstance(t.arg, TFun):
        left = f"({left})"
    return f"{left} {arrow} {show_type(t.res, greek, arrow)}"


def free_vars(t):
    if isinstance(t, TVar):
        return {t.n}
    if isinstance(t, TFun):
        return free_vars(t.arg) | free_vars(t.res)
    return set()


def apply(subst, t):
    if isinstance(t, TVar):
        return subst.get(t.n, t)
    if isinstance(t, TFun):
        return TFun(apply(subst, t.arg), apply(subst, t.res))
    return t


def rename(t, mapping=None):
    """Renames type variables to 0, 1, 2, ... in order of appearance."""
    mapping = {} if mapping is None else mapping
    if isinstance(t, TVar):
        mapping.setdefault(t.n, len(mapping))
        return TVar(mapping[t.n])
    if isinstance(t, TFun):
        a = rename(t.arg, mapping)
        return TFun(a, rename(t.res, mapping))
    return t


def parse_type(text):
    """'int', 'bool', 'int -> bool', ... (only for initial assumptions)."""
    parts = [p.strip() for p in text.split("->")]
    t = TCon(parts[-1])
    for p in reversed(parts[:-1]):
        t = TFun(TCon(p), t)
    return t


# ---------------------------------------------------------------- errors

class MLTypeError(Exception):
    def __init__(self, reason, left, right, protocol):
        self.reason, self.left, self.right, self.protocol = reason, left, right, protocol
        super().__init__(describe(protocol[-1]))


# ---------------------------------------------------------------- inference

@dataclass
class Scheme:
    quantified: frozenset
    type: object


class _Inference:
    def __init__(self, ast):
        self.ast = ast
        self.num = numbering(ast)
        self.next_var = 0
        self.subst = {}            # var number -> type, always fully applied
        self.pending = []          # equations not yet unified: (left, right)
        self.protocol = []

    def fresh(self, node, what="node"):
        v = TVar(self.next_var)
        self.next_var += 1
        self.protocol.append({"kind": "fresh", "node": self.num[id(node)], "var": v,
                              "what": what, "expr": show(node)})
        return v

    def equation(self, node, left, right, reason):
        self.protocol.append({"kind": "equation", "node": self.num[id(node)],
                              "left": left, "right": right, "reason": reason})
        self.pending.append((left, right))

    def solve(self):
        while self.pending:
            left, right = self.pending.pop(0)
            self.unify(left, right, 0)

    def bind(self, var, t):
        single = {var.n: t}
        self.subst = {k: apply(single, v) for k, v in self.subst.items()}
        self.subst[var.n] = t

    def unify(self, t1, t2, depth):
        a, b = apply(self.subst, t1), apply(self.subst, t2)
        step = {"kind": "unify", "left": a, "right": b, "depth": depth, "binding": None}
        if isinstance(a, TVar) and a == b:
            step["case"] = "same variable"
        elif isinstance(a, TVar) or isinstance(b, TVar):
            var, t = (a, b) if isinstance(a, TVar) else (b, a)
            if var.n in free_vars(t):
                self.fail("occurs", var, t)
            self.bind(var, t)
            step["case"] = "variable"
            step["binding"] = (var, t)
        elif isinstance(a, TFun) and isinstance(b, TFun):
            step["case"] = "function"
            step["subst"] = dict(self.subst)
            self.protocol.append(step)
            self.unify(a.arg, b.arg, depth + 1)
            self.unify(a.res, b.res, depth + 1)
            return
        elif a == b:
            step["case"] = "constant"
        else:
            self.fail("mismatch", a, b)
        step["subst"] = dict(self.subst)
        self.protocol.append(step)

    def fail(self, reason, left, right):
        self.protocol.append({"kind": "error", "reason": reason, "left": left, "right": right})
        raise MLTypeError(reason, left, right, self.protocol)

    def generalize(self, env, t):
        t = apply(self.subst, t)
        env_vars = set()
        for s in env.values():
            env_vars |= free_vars(apply(self.subst, s.type)) - s.quantified
        return Scheme(frozenset(free_vars(t) - env_vars), t)

    def visit(self, e, env):
        """Gives node e its type variable, visits the children, emits the equations."""
        alpha = self.fresh(e)
        if isinstance(e, Const):
            self.equation(e, alpha, BOOL if isinstance(e.value, bool) else INT, "constant")
        elif isinstance(e, Var):
            if e.name not in env:
                self.protocol.append({"kind": "error", "reason": "unbound", "left": e.name, "right": None})
                raise MLTypeError("unbound", e.name, None, self.protocol)
            s = env[e.name]
            t = s.type
            if s.quantified:
                inst = {}
                for q in sorted(s.quantified):
                    inst[q] = TVar(self.next_var)
                    self.next_var += 1
                t = apply(inst, apply(self.subst, s.type))
                self.protocol.append({"kind": "instance", "node": self.num[id(e)], "name": e.name,
                                      "scheme": s, "type": t})
            self.equation(e, alpha, t, "variable")
        elif isinstance(e, Fn):
            beta = self.fresh(e, e.param)
            body = self.visit(e.body, {**env, e.param: Scheme(frozenset(), beta)})
            self.equation(e, alpha, TFun(beta, body), "abstraction")
        elif isinstance(e, App):
            f = self.visit(e.fn, env)
            a = self.visit(e.arg, env)
            self.equation(e, f, TFun(a, alpha), "application")
        elif isinstance(e, BinOp):
            left = self.visit(e.left, env)
            right = self.visit(e.right, env)
            self.equation(e, left, INT, "operand")
            self.equation(e, right, INT, "operand")
            self.equation(e, alpha, BOOL if e.op in ("=", "<") else INT, "operator")
        elif isinstance(e, UnOp):
            arg = self.visit(e.arg, env)
            self.equation(e, arg, BOOL, "operand")
            self.equation(e, alpha, BOOL, "operator")
        elif isinstance(e, If):
            c = self.visit(e.cond, env)
            t = self.visit(e.then, env)
            f = self.visit(e.else_, env)
            self.equation(e, c, BOOL, "condition")
            self.equation(e, alpha, t, "then branch")
            self.equation(e, alpha, f, "else branch")
        elif isinstance(e, Let):
            v = self.visit(e.value, env)
            self.solve()
            s = self.generalize(env, v)
            self.protocol.append({"kind": "generalize", "node": self.num[id(e)], "name": e.name,
                                  "type": s.type, "scheme": s})
            body = self.visit(e.body, {**env, e.name: s})
            self.equation(e, alpha, body, "let body")
        elif isinstance(e, LetRec):
            inner = dict(env)
            names = []
            for name, _ in e.bindings:
                phi = self.fresh(e, name)
                inner[name] = Scheme(frozenset(), phi)
                names.append((name, phi))
            for (name, phi), (_, value) in zip(names, e.bindings):
                v = self.visit(value, inner)
                self.equation(e, phi, v, "recursive definition")
            self.solve()
            outer = dict(env)
            for name, phi in names:
                s = self.generalize(env, phi)
                outer[name] = s
                self.protocol.append({"kind": "generalize", "node": self.num[id(e)], "name": name,
                                      "type": s.type, "scheme": s})
            body = self.visit(e.body, outer)
            self.equation(e, alpha, body, "let body")
        else:
            raise TypeError(e)
        return alpha


def infer(program, env=None):
    """Type of a program and the protocol. env: initial assumptions {name: type or 'int'}."""
    ast = as_ast(program)
    inf = _Inference(ast)
    start = {}
    for name, t in (env or {}).items():
        start[name] = Scheme(frozenset(), parse_type(t) if isinstance(t, str) else t)
    root = inf.visit(ast, start)
    inf.solve()
    t = rename(apply(inf.subst, root))
    inf.protocol.append({"kind": "result", "type": t})
    return t, inf.protocol


def type_of(program, env=None, greek=False):
    """Just the type as text."""
    return show_type(infer(program, env)[0], greek)


def show_scheme(s, greek=False):
    t = show_type(s.type, greek)
    if not s.quantified:
        return t
    return "∀" + ",".join(var_name(q, greek) for q in sorted(s.quantified)) + ". " + t


def show_subst(subst, greek=False):
    return "[" + ", ".join(f"{show_type(t, greek)}/{var_name(v, greek)}"
                           for v, t in sorted(subst.items())) + "]"


def describe(step, greek=False):
    """One protocol step as a line of text."""
    T = lambda t: show_type(t, greek)
    k = step["kind"]
    if k == "fresh":
        who = "node" if step["what"] == "node" else f"name {step['what']} of"
        return f"{T(step['var'])}: {who} #{step['node']} {step['expr']}"
    if k == "instance":
        return f"#{step['node']} {step['name']}: instance of {show_scheme(step['scheme'], greek)} is {T(step['type'])}"
    if k == "equation":
        return f"#{step['node']} {step['reason']}: {T(step['left'])} = {T(step['right'])}"
    if k == "unify":
        indent = "  " * step["depth"]
        text = f"{indent}unify {T(step['left'])} with {T(step['right'])} ({step['case']})"
        if step["binding"]:
            v, t = step["binding"]
            text += f": {T(t)}/{T(v)}"
        return text + f"   {show_subst(step['subst'], greek)}"
    if k == "generalize":
        return f"#{step['node']} {step['name']} : {show_scheme(step['scheme'], greek)}"
    if k == "error":
        if step["reason"] == "occurs":
            return f"error: {T(step['left'])} occurs in {T(step['right'])}"
        if step["reason"] == "unbound":
            return f"error: unbound name {step['left']}"
        return f"error: cannot unify {T(step['left'])} with {T(step['right'])}"
    if k == "result":
        return f"type: {T(step['type'])}"
    raise ValueError(k)


if __name__ == "__main__":
    greek = "--greek" in sys.argv
    src = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    try:
        _, protocol = infer(src)
    except MLTypeError as err:
        protocol = err.protocol
    for step in protocol:
        print(describe(step, greek))
