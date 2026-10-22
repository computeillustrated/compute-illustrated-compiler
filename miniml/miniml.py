"""Mini-ML: lexer, parser, abstract syntax and pretty printer.

Syntax (ASCII, Standard ML style):

    e ::= n | true | false | x
        | fn x => e
        | e e                          application, left-associative
        | e + e | e - e | e * e        integers
        | e = e | e < e                comparisons (int -> int -> bool)
        | not e                        (applies to an atom, like application)
        | if e then e else e
        | let val x = e in e end
        | let val rec f = fn x => e and g = fn y => e in e end
        | let fun f x y = e and g z = e in e end    (sugar for val rec)

Precedence from weakest to strongest: fn/if/let, = <, + -, *, application.

Usage:  python miniml.py "let val x = 10 + 2 * 3 in x end"
"""

import re
import sys
from dataclasses import dataclass, field


# ---------------------------------------------------------------- AST

@dataclass(eq=False)
class Const:
    value: object          # int or bool


@dataclass(eq=False)
class Var:
    name: str


@dataclass(eq=False)
class Fn:
    param: str
    body: object


@dataclass(eq=False)
class App:
    fn: object
    arg: object


@dataclass(eq=False)
class BinOp:
    op: str                # '+', '-', '*', '=', '<'
    left: object
    right: object


@dataclass(eq=False)
class UnOp:
    op: str                # 'not'
    arg: object


@dataclass(eq=False)
class If:
    cond: object
    then: object
    else_: object


@dataclass(eq=False)
class Let:
    name: str
    value: object
    body: object


@dataclass(eq=False)
class LetRec:
    bindings: list         # list of (name, Fn)
    body: object


# ---------------------------------------------------------------- lexer

KEYWORDS = {"fn", "let", "val", "rec", "fun", "and", "in", "end",
            "if", "then", "else", "true", "false", "not"}
TOKEN_RE = re.compile(r"\s*(?:(\d+)|([A-Za-z_][A-Za-z0-9_']*)|(=>|[=+\-*<()]))")


class MLSyntaxError(Exception):
    pass


def tokens(text):
    """List of (kind, value): kind is 'num', 'id', 'kw' or 'sym'; ends with ('eof', None)."""
    result, pos = [], 0
    text = text.rstrip()
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise MLSyntaxError(f"unexpected character {text[pos:].strip()[:1]!r} at {pos}")
        num, ident, sym = m.groups()
        if num is not None:
            result.append(("num", int(num)))
        elif ident is not None:
            result.append(("kw" if ident in KEYWORDS else "id", ident))
        else:
            result.append(("sym", sym))
        pos = m.end()
    result.append(("eof", None))
    return result


# ---------------------------------------------------------------- parser

class _Parser:
    def __init__(self, text):
        self.toks = tokens(text)
        self.pos = 0

    def peek(self):
        return self.toks[self.pos]

    def is_(self, kind, value=None):
        k, v = self.peek()
        return k == kind and (value is None or v == value)

    def take(self, kind, value=None):
        if not self.is_(kind, value):
            want = value if value is not None else kind
            raise MLSyntaxError(f"expected {want!r}, found {self.peek()[1]!r}")
        tok = self.toks[self.pos]
        self.pos += 1
        return tok[1]

    def expr(self):
        if self.is_("kw", "fn"):
            self.take("kw", "fn")
            x = self.take("id")
            self.take("sym", "=>")
            return Fn(x, self.expr())
        if self.is_("kw", "if"):
            self.take("kw", "if")
            c = self.expr()
            self.take("kw", "then")
            t = self.expr()
            self.take("kw", "else")
            return If(c, t, self.expr())
        if self.is_("kw", "let"):
            return self.let()
        return self.compare()

    def let(self):
        self.take("kw", "let")
        if self.is_("kw", "fun"):
            bindings = []
            while True:
                self.take("kw", "fun" if not bindings else "and")
                name = self.take("id")
                params = [self.take("id")]
                while self.is_("id"):
                    params.append(self.take("id"))
                self.take("sym", "=")
                body = self.expr()
                for p in reversed(params):
                    body = Fn(p, body)
                bindings.append((name, body))
                if not self.is_("kw", "and"):
                    break
            self.take("kw", "in")
            body = self.expr()
            self.take("kw", "end")
            return LetRec(bindings, body)
        self.take("kw", "val")
        if self.is_("kw", "rec"):
            self.take("kw", "rec")
            bindings = []
            while True:
                if bindings:
                    self.take("kw", "and")
                name = self.take("id")
                self.take("sym", "=")
                value = self.expr()
                if not isinstance(value, Fn):
                    raise MLSyntaxError(f"val rec {name}: only fn expressions may be defined recursively")
                bindings.append((name, value))
                if not self.is_("kw", "and"):
                    break
            self.take("kw", "in")
            body = self.expr()
            self.take("kw", "end")
            return LetRec(bindings, body)
        name = self.take("id")
        self.take("sym", "=")
        value = self.expr()
        self.take("kw", "in")
        body = self.expr()
        self.take("kw", "end")
        return Let(name, value, body)

    def compare(self):
        left = self.additive()
        if self.is_("sym", "=") or self.is_("sym", "<"):
            op = self.take("sym")
            return BinOp(op, left, self.additive())
        return left

    def additive(self):
        left = self.multiplicative()
        while self.is_("sym", "+") or self.is_("sym", "-"):
            op = self.take("sym")
            left = BinOp(op, left, self.multiplicative())
        return left

    def multiplicative(self):
        left = self.application()
        while self.is_("sym", "*"):
            self.take("sym")
            left = BinOp("*", left, self.application())
        return left

    def starts_atom(self):
        k, v = self.peek()
        return k in ("num", "id") or (k == "kw" and v in ("true", "false", "not")) \
            or (k == "sym" and v == "(")

    def application(self):
        e = self.atom()
        while self.starts_atom():
            e = App(e, self.atom())
        return e

    def atom(self):
        k, v = self.peek()
        if k == "num":
            self.pos += 1
            return Const(v)
        if k == "kw" and v in ("true", "false"):
            self.pos += 1
            return Const(v == "true")
        if k == "kw" and v == "not":
            self.pos += 1
            return UnOp("not", self.atom())
        if k == "id":
            self.pos += 1
            return Var(v)
        if k == "sym" and v == "(":
            self.pos += 1
            e = self.expr()
            self.take("sym", ")")
            return e
        raise MLSyntaxError(f"unexpected {v!r}")


def parse(text):
    """Source text -> AST."""
    p = _Parser(text)
    e = p.expr()
    p.take("eof")
    return e


def as_ast(program):
    """Accepts source text or an AST."""
    return parse(program) if isinstance(program, str) else program


# ---------------------------------------------------------------- printing

def _level(e):
    if isinstance(e, (Fn, If, Let, LetRec)):
        return 0
    if isinstance(e, BinOp):
        return {"=": 1, "<": 1, "+": 2, "-": 2, "*": 3}[e.op]
    if isinstance(e, (App, UnOp)):
        return 4
    return 5


def show(e, ctx=0):
    """Canonical source text (minimal parentheses, one line)."""
    e = as_ast(e)
    if isinstance(e, Const):
        s = ("true" if e.value else "false") if isinstance(e.value, bool) else str(e.value)
    elif isinstance(e, Var):
        s = e.name
    elif isinstance(e, Fn):
        s = f"fn {e.param} => {show(e.body)}"
    elif isinstance(e, App):
        s = f"{show(e.fn, 4)} {show(e.arg, 5)}"
    elif isinstance(e, UnOp):
        s = f"{e.op} {show(e.arg, 5)}"
    elif isinstance(e, BinOp):
        lv = _level(e)
        if e.op in ("=", "<"):
            s = f"{show(e.left, 2)} {e.op} {show(e.right, 2)}"
        else:
            s = f"{show(e.left, lv)} {e.op} {show(e.right, lv + 1)}"
    elif isinstance(e, If):
        s = f"if {show(e.cond)} then {show(e.then)} else {show(e.else_)}"
    elif isinstance(e, Let):
        s = f"let val {e.name} = {show(e.value)} in {show(e.body)} end"
    elif isinstance(e, LetRec):
        defs = " and ".join(f"{n} = {show(v)}" for n, v in e.bindings)
        s = f"let val rec {defs} in {show(e.body)} end"
    else:
        raise TypeError(e)
    return f"({s})" if _level(e) < ctx else s


zeige = show


# ---------------------------------------------------------------- tree

def children(e):
    """Child expressions in evaluation order of the source (left to right)."""
    if isinstance(e, Fn):
        return [e.body]
    if isinstance(e, App):
        return [e.fn, e.arg]
    if isinstance(e, BinOp):
        return [e.left, e.right]
    if isinstance(e, UnOp):
        return [e.arg]
    if isinstance(e, If):
        return [e.cond, e.then, e.else_]
    if isinstance(e, Let):
        return [e.value, e.body]
    if isinstance(e, LetRec):
        return [v for _, v in e.bindings] + [e.body]
    return []


def label(e):
    """Short label of a tree node."""
    if isinstance(e, Const):
        return show(e)
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Fn):
        return f"fn {e.param}"
    if isinstance(e, App):
        return "@"
    if isinstance(e, (BinOp, UnOp)):
        return e.op
    if isinstance(e, If):
        return "if"
    if isinstance(e, Let):
        return f"let {e.name}"
    if isinstance(e, LetRec):
        return "let rec " + ", ".join(n for n, _ in e.bindings)
    raise TypeError(e)


def tree(e):
    """Expression tree as nested (label, [children]) tuples."""
    e = as_ast(e)
    return (label(e), [tree(c) for c in children(e)])


def nodes(e):
    """All nodes in preorder; the index in this list is the node number used in protocols."""
    e = as_ast(e)
    result = [e]
    for c in children(e):
        result.extend(nodes(c))
    return result


def numbering(e):
    """dict id(node) -> preorder number."""
    return {id(n): i for i, n in enumerate(nodes(e))}


if __name__ == "__main__":
    ast = parse(sys.argv[1])
    print(show(ast))
    print(tree(ast))
