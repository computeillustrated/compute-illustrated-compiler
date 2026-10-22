"""One expression in all the intermediate representations.

Input is an assignment in the calculator's language, e.g. "y = x * 2 + x * 2 * 3".
Computed are:
  parse_tree()        concrete syntax tree with the nonterminals from calc.y
                      (statement, expr, term, factor; tokens NUMBER, IDENT, PLUS …)
  ast()               abstract syntax tree: only operators and operands are left
  dag()               directed acyclic graph: equal subtrees only once
  postfix()           postfix: target first, "=" at the end
  three_address()     three-address code from the AST (one instruction per operator) or the DAG
  quadruples(), triples(), indirect_triples()   the three table forms of 3AC

The parser here is a small one of its own with the same rules as calc.y (loops instead of
left recursion, but the tree is built left-recursively as Bison does).
test_representations.py checks that it makes the same reductions as the real calculator
(yydebug trace) and that three_address() prints the same as `calc -t`.

Usage:  python representations.py "y = x * 2 + x * 2 * 3"
"""
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

TOKENS = [("NUMBER", r"\d+(\.\d+)?"), ("IDENT", r"[a-zA-Z][a-zA-Z0-9]*"), ("PLUS", r"\+"),
          ("MINUS", r"-"), ("TIMES", r"\*"), ("DIVIDE", r"/"), ("LPAREN", r"\("),
          ("RPAREN", r"\)"), ("ASSIGN", r"=")]
OPERATOR = {"PLUS": "+", "MINUS": "-", "TIMES": "*", "DIVIDE": "/"}


def tokenize(text):
    """[(name, lexeme), …] like the calculator's scanner."""
    result, pos = [], 0
    while pos < len(text):
        if text[pos] in " \t":
            pos += 1
            continue
        for name, pattern in TOKENS:
            if m := re.match(pattern, text[pos:]):
                result.append((name, m[0]))
                pos += len(m[0])
                break
        else:
            raise ValueError(f"unknown character: {text[pos]}")
    return result


# --- Concrete syntax tree ----------------------------------------------------------

@dataclass(eq=False)
class Node:
    """A node of the concrete syntax tree: a nonterminal with children or a token with its lexeme."""
    symbol: str
    text: Optional[str] = None
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for k in self.children:
            yield from k.walk()

    def reductions(self):
        """(left, [right…]) in the order a bottom-up parser reduces
        (post-order of the inner nodes)."""
        for k in self.children:
            yield from k.reductions()
        if self.text is None:
            yield self.symbol, [k.symbol for k in self.children]

    def lines(self, depth=0):
        """Indented text form, one line per node."""
        head = f"{self.symbol}[{self.text}]" if self.text is not None else self.symbol
        yield "  " * depth + head
        for k in self.children:
            yield from k.lines(depth + 1)


class _Parser:
    def __init__(self, text):
        self.t = tokenize(text)
        self.i = 0

    def sees(self, *names):
        return self.i < len(self.t) and self.t[self.i][0] in names

    def take(self, name):
        if not self.sees(name):
            raise SyntaxError(f"expected {name} at {self.t[self.i:]}")
        self.i += 1
        return Node(name, self.t[self.i - 1][1])

    def statement(self):
        target, assign = self.take("IDENT"), self.take("ASSIGN")
        node = Node("statement", None, [target, assign, self.expr(), Node("NEWLINE", "\\n")])
        if self.i != len(self.t):
            raise SyntaxError(f"left over after the assignment: {self.t[self.i:]}")
        return node

    def expr(self):
        left = Node("expr", None, [self.term()])
        while self.sees("PLUS", "MINUS"):
            op = self.take(self.t[self.i][0])
            left = Node("expr", None, [left, op, self.term()])
        return left

    def term(self):
        left = Node("term", None, [self.factor()])
        while self.sees("TIMES", "DIVIDE"):
            op = self.take(self.t[self.i][0])
            left = Node("term", None, [left, op, self.factor()])
        return left

    def factor(self):
        if self.sees("NUMBER"):
            return Node("factor", None, [self.take("NUMBER")])
        if self.sees("IDENT"):
            return Node("factor", None, [self.take("IDENT")])
        return Node("factor", None, [self.take("LPAREN"), self.expr(), self.take("RPAREN")])


def parse_tree(line):
    """Concrete syntax tree of an assignment, root `statement` (rule from calc.y:
    statement : IDENT ASSIGN expr NEWLINE)."""
    return _Parser(line).statement()


# --- AST ----------------------------------------------------------------------------

@dataclass(eq=False)
class Ast:
    """A node of the abstract syntax tree: an operator ("+", "*", "=", …) with children,
    or a leaf (number or name) without children."""
    label: str
    children: list = field(default_factory=list)
    source: Optional[Node] = None       # node of the parse tree it came from

    @property
    def is_leaf(self):
        return not self.children

    def walk(self):
        yield self
        for k in self.children:
            yield from k.walk()

    def lines(self, depth=0):
        yield "  " * depth + self.label
        for k in self.children:
            yield from k.lines(depth + 1)


def ast(tree):
    """From the parse tree: chains like expr → term → factor → NUMBER shrink to a leaf,
    parentheses disappear, every operator becomes a node with its operands."""
    def strip(k):
        if k.text is not None:
            return Ast(k.text, [], k)
        if k.symbol == "statement":
            target, _, expression, _ = k.children
            return Ast("=", [strip(target), strip(expression)], k)
        if len(k.children) == 1:
            return strip(k.children[0])
        if k.children[0].symbol == "LPAREN":
            return strip(k.children[1])
        return Ast(OPERATOR[k.children[1].symbol], [strip(k.children[0]), strip(k.children[2])], k)
    return strip(tree)


# --- DAG ----------------------------------------------------------------------------

@dataclass
class Dag:
    """Nodes numbered from 0 in the order they are created (post-order of the AST).
    nodes[i] = (label, (child numbers …)); to_dag[id(ast_node)] = number in the DAG."""
    nodes: list
    to_dag: dict
    root: int

    def parents(self, i):
        return [j for j, (_, children) in enumerate(self.nodes) if i in children]

    def shared(self):
        """Numbers of the nodes with more than one parent (or used twice by the same parent)."""
        count = {}
        for _, children in self.nodes:
            for k in children:
                count[k] = count.get(k, 0) + 1
        return sorted(k for k, n in count.items() if n > 1)

    def lines(self):
        for i, (label, children) in enumerate(self.nodes):
            yield f"n{i}: {label}" + (f"({', '.join(f'n{k}' for k in children)})" if children else "")


def dag(tree_ast):
    """Value numbering: a node with the same label and the same children is not created
    again but reused. So equal leaves (2 and 2) merge as well."""
    nodes, number, to_dag = [], {}, {}

    def build(a):
        key = (a.label, tuple(build(k) for k in a.children))
        if key not in number:
            number[key] = len(nodes)
            nodes.append(key)
        to_dag[id(a)] = number[key]
        return number[key]
    return Dag(nodes, to_dag, build(tree_ast))


# --- Postfix ------------------------------------------------------------------------

def postfix(tree_ast):
    """Postfix like the translator built with yacc: `x 10 2 3 * + =`. For "=" the target
    comes first (it is read first), the operands follow, the operator comes last."""
    if tree_ast.is_leaf:
        return [tree_ast.label]
    return [w for k in tree_ast.children for w in postfix(k)] + [tree_ast.label]


# --- Three-address code -------------------------------------------------------------

@dataclass(frozen=True)
class Instr:
    """target := a op b   or   target := a (op None)"""
    target: str
    a: str
    op: Optional[str] = None
    b: Optional[str] = None

    def __str__(self):
        return f"{self.target} := {self.a}" if self.op is None else f"{self.target} := {self.a} {self.op} {self.b}"


def three_address(tree_ast, from_dag=False, first_temp=1):
    """One instruction per operator, intermediate results in t1, t2, … (post-order, left
    first). Leaves are their own place, as in the calculator's generator.
    from_dag=True: a DAG node that was computed already is not computed again, its t is
    reused. first_temp: number of the first temporary (the calculator counts across the
    whole program)."""
    d = dag(tree_ast) if from_dag else None
    code, done = [], {}

    def gen(a):
        if a.is_leaf:
            return a.label
        if d is not None and d.to_dag[id(a)] in done:
            return done[d.to_dag[id(a)]]
        x, y = (gen(k) for k in a.children)
        t = f"t{first_temp + sum(1 for c in code if c.target.startswith('t'))}"
        code.append(Instr(t, x, a.label, y))
        if d is not None:
            done[d.to_dag[id(a)]] = t
        return t

    target, expression = tree_ast.children
    code.append(Instr(target.label, gen(expression)))
    return code


def quadruples(code):
    """(op, arg1, arg2, result); a copy has op ":=" and no arg2."""
    return [(":=" if c.op is None else c.op, c.a, c.b or "", c.target) for c in code]


def triples(code):
    """(op, arg1, arg2) without a result field: an intermediate result is referred to by the
    number of the triple that computes it: "(0)". A copy into a variable becomes
    (":=", variable, value). Numbers from 0."""
    where = {}
    rows = []
    for c in code:
        ref = lambda x: f"({where[x]})" if x in where else x
        if c.op is None:
            rows.append((":=", c.target, ref(c.a)))
        else:
            rows.append((c.op, ref(c.a), ref(c.b)))
        if c.target.startswith("t") and c.target[1:].isdigit():
            where[c.target] = len(rows) - 1
    return rows


def indirect_triples(code, order=None):
    """(statement list, triples): the list names the triples in execution order. An optimizer
    can reorder it (order) without changing any reference "(i)" inside the triples."""
    t = triples(code)
    return (list(order) if order is not None else list(range(len(t)))), t


# --- Stack code ---------------------------------------------------------------------

STACK_OP = {"+": "add", "-": "sub", "*": "mul", "/": "div"}


def stack_code(tree_ast):
    """Code for the stack machine, instruction by instruction from the postfix: target →
    lvar x (address), name → var x (value), number → const 10, operator → add/sub/mul/div,
    "=" → store. For an expression without assignment pass the expression node."""
    instructions = []

    def gen(a, is_target=False):
        if a.is_leaf:
            if is_target:
                instructions.append(("lvar", a.label))
            elif re.fullmatch(r"\d+(\.\d+)?", a.label):
                instructions.append(("const", a.label))
            else:
                instructions.append(("var", a.label))
        elif a.label == "=":
            gen(a.children[0], True)
            gen(a.children[1])
            instructions.append(("store", None))
        else:
            gen(a.children[0])
            gen(a.children[1])
            instructions.append((STACK_OP[a.label], None))
    gen(tree_ast)
    return instructions


def all_forms(line, first_temp=1):
    """All representations of a line as a dict."""
    tree = parse_tree(line)
    a = ast(tree)
    d = dag(a)
    code = three_address(a, first_temp=first_temp)
    code_dag = three_address(a, from_dag=True, first_temp=first_temp)
    return {"line": line, "tokens": tokenize(line), "parse_tree": tree, "ast": a, "dag": d,
            "postfix": postfix(a), "tac": code, "tac_dag": code_dag,
            "quadruples": quadruples(code), "triples": triples(code),
            "indirect_triples": indirect_triples(code), "stack_code": stack_code(a),
            "node_count": {"parse_tree": sum(1 for _ in tree.walk()), "ast": sum(1 for _ in a.walk()),
                           "dag": len(d.nodes)}}


def main():
    r = all_forms(sys.argv[1])
    print("Parse tree:", *r["parse_tree"].lines(), sep="\n  ")
    print("AST:", *r["ast"].lines(), sep="\n  ")
    print("DAG:", *r["dag"].lines(), f"shared: {['n%d' % i for i in r['dag'].shared()]}", sep="\n  ")
    print("Postfix:", " ".join(r["postfix"]))
    print("3AC (AST):", *map(str, r["tac"]), sep="\n  ")
    print("3AC (DAG):", *map(str, r["tac_dag"]), sep="\n  ")
    print("Quadruples:", *(f"({i}) {q}" for i, q in enumerate(r["quadruples"])), sep="\n  ")
    print("Triples:", *(f"({i}) {t}" for i, t in enumerate(r["triples"])), sep="\n  ")
    print("Stack code:", *(f"{b} {a}" if a else b for b, a in r["stack_code"]), sep="\n  ")
    print("Nodes:", r["node_count"])


if __name__ == "__main__":
    main()
