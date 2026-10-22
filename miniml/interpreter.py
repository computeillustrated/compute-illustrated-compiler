"""Mini-ML interpreter with environments and closures (call by value, static binding).

An environment is a list of bindings (name, value), newest first. A function value is
a closure: the fn expression together with the environment it was created in. A
recursive let builds a cyclic environment: the closure's environment contains the
binding of the closure itself.

    value, protocol = evaluate("(fn i => i * 2) z", {"z": 7})

Protocol: list of dicts, one when an expression is entered and one when it is done:
    event  "enter" or "exit"
    rule   const, var, fn, app, prim, if, let, letrec
           (on exit of if: "if true" / "if false")
    node   preorder number of the expression (see miniml.nodes)
    expr   the expression as text
    env    list of (name, value as text), newest first
    depth  nesting depth (0 = whole program)
    value  result as text (exit only)

Usage:  python interpreter.py "(fn i => i * 2) z" z=7
"""

import sys
from dataclasses import dataclass

from miniml import (App, BinOp, Const, Fn, If, Let, LetRec, UnOp, Var,
                    as_ast, numbering, show)


@dataclass(eq=False)
class Closure:
    fn: Fn
    env: list              # list of (name, value)


def show_value(v, nested=False):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if nested:
        return f"({show(v.fn)}, …)"
    return f"({show(v.fn)}, {show_env(v.env, nested=True)})"


def show_env(env, nested=False):
    return "[" + ", ".join(f"{n} ↦ {show_value(v, nested)}" for n, v in env) + "]"


RULES = {Const: "const", Var: "var", Fn: "fn", App: "app", BinOp: "prim", UnOp: "prim",
         If: "if", Let: "let", LetRec: "letrec"}

PRIMITIVES = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
              "=": lambda a, b: a == b, "<": lambda a, b: a < b}


class _Interpreter:
    def __init__(self, ast):
        self.num = numbering(ast)
        self.protocol = []

    def log(self, event, rule, e, env, depth, value=None):
        step = {"event": event, "rule": rule, "node": self.num.get(id(e)), "expr": show(e),
                "env": [(n, show_value(v)) for n, v in env], "depth": depth}
        if event == "exit":
            step["value"] = show_value(value)
            step["result"] = value
        self.protocol.append(step)

    def lookup(self, name, env):
        for n, v in env:
            if n == name:
                return v
        raise NameError(f"unbound name {name}")

    def eval(self, e, env, depth):
        rule = RULES[type(e)]
        self.log("enter", rule, e, env, depth)
        if isinstance(e, Const):
            v = e.value
        elif isinstance(e, Var):
            v = self.lookup(e.name, env)
        elif isinstance(e, Fn):
            v = Closure(e, env)
        elif isinstance(e, BinOp):
            a = self.eval(e.left, env, depth + 1)
            b = self.eval(e.right, env, depth + 1)
            v = PRIMITIVES[e.op](a, b)
        elif isinstance(e, UnOp):
            v = not self.eval(e.arg, env, depth + 1)
        elif isinstance(e, If):
            c = self.eval(e.cond, env, depth + 1)
            rule = "if true" if c else "if false"
            v = self.eval(e.then if c else e.else_, env, depth + 1)
        elif isinstance(e, App):
            f = self.eval(e.fn, env, depth + 1)
            a = self.eval(e.arg, env, depth + 1)
            v = self.eval(f.fn.body, [(f.fn.param, a)] + f.env, depth + 1)
        elif isinstance(e, Let):
            a = self.eval(e.value, env, depth + 1)
            v = self.eval(e.body, [(e.name, a)] + env, depth + 1)
        elif isinstance(e, LetRec):
            # cyclic environment: the closures get the environment that contains them
            new_env = []
            closures = [Closure(fn, new_env) for _, fn in e.bindings]
            new_env.extend([(n, c) for (n, _), c in zip(e.bindings, closures)] + env)
            v = self.eval(e.body, new_env, depth + 1)
        else:
            raise TypeError(e)
        self.log("exit", rule, e, env, depth, v)
        return v


def evaluate(program, env=None):
    """Value and protocol. env: {name: value} or list of (name, value), newest first."""
    ast = as_ast(program)
    start = list(env.items()) if isinstance(env, dict) else list(env or [])
    interp = _Interpreter(ast)
    v = interp.eval(ast, start, 0)
    return v, interp.protocol


def describe(step):
    indent = "  " * step["depth"]
    env = "[" + ", ".join(f"{n} ↦ {v}" for n, v in step["env"]) + "]"
    if step["event"] == "enter":
        return f"{indent}{step['rule']}: {step['expr']}   in {env}"
    return f"{indent}= {step['value']}   ({step['rule']}: {step['expr']})"


if __name__ == "__main__":
    env = {}
    for a in sys.argv[2:]:
        n, v = a.split("=")
        env[n] = {"true": True, "false": False}.get(v) if v in ("true", "false") else int(v)
    value, protocol = evaluate(sys.argv[1], env)
    for step in protocol:
        print(describe(step))
