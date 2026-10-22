"""Machine-independent optimizations on three-address code.

Every optimization takes a `Code` and returns a `Result`: the code before and after and a
log with one entry per change (original line number, rule, instruction before and after).
Nothing changes the input. `check(result)` runs both versions on the 3AC machine and
compares the printed output and the final values of main's variables.

Local (inside one basic block):
    constant_folding, constant_propagation, copy_propagation, algebraic_simplification,
    strength_reduction (x * 2 -> x + x), common_subexpressions (value numbering = DAG),
    inline_expansion (a call is replaced by the body of the function)
Loops and global (need the flow graph and data-flow analysis):
    loop_invariant_code_motion, induction_variables, loop_unrolling,
    dead_code_elimination (unreachable blocks, assignments to dead variables),
    code_hoisting (very busy expressions move up into the branching block)

Usage:  python optimize.py gemeinsam common_subexpressions
        python optimize.py sortieren all       every optimization on its own
        python optimize.py ausdruck pipeline    local passes + dead code until nothing changes
"""
import sys
from collections import Counter
from dataclasses import dataclass, field

from blocks import tac  # noqa: F401  (blocks puts the folder of tac.py on the path)
from blocks import (Line, build, expression, flow_graph, is_const, is_var, load, operands,
                     parse, replace_operands, target)
from dataflow import dead_assignments, live_variables, very_busy_expressions


@dataclass
class Change:
    line: int                   # original line number (None: a new instruction)
    rule: str
    before: str                 # None: inserted
    after: str                  # None: removed

    def __str__(self):
        where = f"line {self.line:3}" if self.line else "new     "
        b = self.before or "-"
        a = self.after or "(removed)"
        return f"{where}  {b:<22} => {a:<22} {self.rule}"


@dataclass
class Result:
    name: str
    before: object
    after: object
    log: list = field(default_factory=list)

    def report(self):
        out = [f"{self.name}: {len(self.log)} change(s), "
               f"{len(self.before.lines)} -> {len(self.after.lines)} instructions"]
        out += [f"  {c}" for c in self.log]
        return "\n".join(out)

    def side_by_side(self):
        left = self.before.listing().splitlines()
        right = self.after.listing().splitlines()
        n = max(len(left), len(right))
        left += [""] * (n - len(left))
        right += [""] * (n - len(right))
        return "\n".join(f"{a:<30} | {b}" for a, b in zip(left, right))


def check(result):
    """True if before and after print the same and leave main's variables equal."""
    return result.before.run() == result.after.run()


def literal(v):
    """3AC constant for a value, None if the 3AC cannot write it (negative numbers)."""
    if isinstance(v, int):
        return str(v) if v >= 0 else None
    if v < 0 or v != v or v in (float("inf"),):
        return None
    return repr(v)


def _start(name, code):
    return Result(name, code, code.copy())


def _globals_in(code, proc):
    return {v for v in code.globals_() if code.is_global(v, proc)}


def _blocks(code):
    fg = flow_graph(code)
    return fg, [(b, [code.lines[i] for i in b.indices()]) for b in fg.blocks]


def _set(res, line, new, rule):
    """Changes (or removes, new=None) one line of res.after and logs it."""
    res.log.append(Change(line.nr, rule, line.instr, new))
    line.instr = new


# --- local ---------------------------------------------------------------------------------

def constant_folding(code):
    """a op b with two constants is computed at compile time; a condition with two constants
    becomes `goto` (true) or disappears (false)."""
    res = _start("constant folding", code)
    for line in res.after.lines:
        form, p = parse(line.instr)
        if form == "arith" and is_const(p[1]) and is_const(p[3]):
            try:
                v = tac.compute(tac.number(p[1]), p[2], tac.number(p[3]))
            except tac.TacError:
                continue
            if literal(v) is not None:
                _set(res, line, f"{p[0]} := {literal(v)}", f"{p[1]} {p[2]} {p[3]} = {literal(v)}")
        elif form == "convert" and is_const(p[1]):
            v = float(tac.number(p[1]))
            _set(res, line, f"{p[0]} := {literal(v)}", f"inttofloat {p[1]} = {literal(v)}")
        elif form == "if" and is_const(p[0]) and is_const(p[2]):
            a, b = tac.number(p[0]), tac.number(p[2])
            if tac.type_of(a) != tac.type_of(b):
                continue
            if tac.COMPARE[p[1]](a, b):
                _set(res, line, f"goto {p[3]}", f"{p[0]} {p[1]} {p[2]} is always true")
            else:
                _set(res, line, None, f"{p[0]} {p[1]} {p[2]} is always false")
    res.after.compact()
    return res


def constant_propagation(code):
    """After `x := c` (c a constant) every read of x in the same block reads c, until x is
    assigned again (or a call may change it)."""
    res = _start("constant propagation", code)
    fg, blocks = _blocks(res.after)
    for b, lines in blocks:
        consts = {}
        for line in lines:
            new = replace_operands(line.instr, consts)
            if new != line.instr:
                used = [f"{v} = {c}" for v, c in consts.items() if v in operands(line.instr)]
                _set(res, line, new, "constant " + ", ".join(used))
            form, p = parse(line.instr)
            if form in ("call", "call_value"):
                for v in _globals_in(res.after, b.proc):
                    consts.pop(v, None)
            t = target(line.instr)
            if t:
                consts.pop(t, None)
                if form == "copy" and is_const(p[1]):
                    consts[t] = p[1]
    return res


def copy_propagation(code):
    """After `x := y` (y a variable) reads of x read y instead, until x or y changes. The copy
    itself often becomes dead (dead_code_elimination removes it)."""
    res = _start("copy propagation", code)
    fg, blocks = _blocks(res.after)
    for b, lines in blocks:
        copies = {}
        for line in lines:
            new = replace_operands(line.instr, copies)
            if new != line.instr:
                used = [f"{v} = {c}" for v, c in copies.items() if v in operands(line.instr)]
                _set(res, line, new, "copy " + ", ".join(used))
            form, p = parse(line.instr)
            killed = set()
            if form in ("call", "call_value"):
                killed |= _globals_in(res.after, b.proc)
            t = target(line.instr)
            if t:
                killed.add(t)
            copies = {x: y for x, y in copies.items() if x not in killed and y not in killed}
            if form == "copy" and is_var(p[1]) and p[1] != t:
                copies[t] = p[1]
    return res


def algebraic_simplification(code):
    """x + 0, 0 + x, x - 0, x * 1, 1 * x, x / 1 -> x;  x * 0, 0 * x -> 0."""
    res = _start("algebraic simplification", code)
    for line in res.after.lines:
        form, p = parse(line.instr)
        if form != "arith":
            continue
        x, a, op, b = p
        za, zb = tac.number(a), tac.number(b)
        new = None
        if (op in "+-" and zb == 0) or (op in "*/" and zb == 1):
            new, rule = a, f"{a} {op} {b} = {a}"
        elif (op == "+" and za == 0) or (op == "*" and za == 1):
            new, rule = b, f"{a} {op} {b} = {b}"
        elif op == "*" and (za == 0 or zb == 0):
            new = a if za == 0 else b
            rule = f"{a} {op} {b} = {new}"
        if new is not None:
            _set(res, line, f"{x} := {new}", rule)
    return res


def strength_reduction(code):
    """x * 2 and 2 * x become x + x: an addition is cheaper than a multiplication."""
    res = _start("strength reduction", code)
    for line in res.after.lines:
        form, p = parse(line.instr)
        if form == "arith" and p[2] == "*":
            x, a, _, b = p
            if tac.number(b) == 2 and is_var(a):
                _set(res, line, f"{x} := {a} + {a}", f"{a} * 2 = {a} + {a}")
            elif tac.number(a) == 2 and is_var(b):
                _set(res, line, f"{x} := {b} + {b}", f"2 * {b} = {b} + {b}")
    return res


class _Numbering:
    """Value numbers for one basic block: equal number = equal value. This is the DAG of the
    block: every number is a node, leaves are the initial values of variables and constants."""

    def __init__(self):
        self.var = {}           # variable -> number of its current value
        self.const = {}         # constant -> number
        self.expr = {}          # (op, n1, n2) -> number
        self.nodes = []         # number -> {"label", "children", "names"}
        self.version = Counter()  # array -> version (bumped by every store)

    def new(self, label, children=()):
        self.nodes.append({"label": label, "children": list(children), "names": []})
        return len(self.nodes) - 1

    def of(self, arg):
        if is_const(arg):
            if arg not in self.const:
                self.const[arg] = self.new(arg)
            return self.const[arg]
        if arg not in self.var:
            self.var[arg] = self.new(f"{arg}0")
            self.nodes[self.var[arg]]["names"].append(arg)
        return self.var[arg]

    def assign(self, name, n):
        old = self.var.get(name)
        if old is not None and name in self.nodes[old]["names"]:
            self.nodes[old]["names"].remove(name)
        self.var[name] = n
        self.nodes[n]["names"].append(name)

    def holder(self, n, besides):
        return next((v for v in self.nodes[n]["names"] if v != besides), None)

    def lookup(self, key, label, children):
        """(number, existed before)."""
        if key in self.expr:
            return self.expr[key], True
        self.expr[key] = self.new(label, children)
        return self.expr[key], False


def _number_block(code, block, lines, rewrite=None):
    """Runs value numbering over a block; rewrite(line, holder, n) is called for every
    recomputation of a value that a variable still holds."""
    vn = _Numbering()
    for line in lines:
        form, p = parse(line.instr)
        key = None
        if form == "arith":
            a, b = vn.of(p[1]), vn.of(p[3])
            ops = tuple(sorted((a, b))) if p[2] in "+*" else (a, b)
            key, label, children = (p[2],) + ops, p[2], (a, b)
        elif form == "convert":
            a = vn.of(p[1])
            key, label, children = ("inttofloat", a), "inttofloat", (a,)
        elif form == "array_read":
            i = vn.of(p[2])
            key, label, children = ("[]", p[1], vn.version[p[1]], i), f"{p[1]}[]", (i,)
        if key is not None:
            n, existed = vn.lookup(key, label, children)
            h = vn.holder(n, p[0]) if existed else None
            if h and rewrite:
                rewrite(line, h, n)
            vn.assign(p[0], n)
        elif form == "copy":
            vn.assign(p[0], vn.of(p[1]))
        elif form == "array_write":
            vn.version[p[0]] += 1
        elif form in ("call", "call_value"):
            for v in _globals_in(code, block.proc):
                vn.assign(v, vn.new(f"{v}?"))
            for arr in list(vn.version) + [e.name for e in code.frames["main"].entries.values() if e.length]:
                vn.version[arr] += 1
            if form == "call_value":
                vn.assign(p[0], vn.new(f"call {p[1]}"))
    return vn


def dag(code, block_name):
    """The DAG of a basic block: [{"label", "children", "names"}], index = node number.
    Leaves are x0 (value of x at block entry) and constants; names = variables that hold
    the node's value at the end of the block."""
    fg = flow_graph(code)
    b = fg.block(block_name)
    return _number_block(code, b, [code.lines[i] for i in b.indices()]).nodes


def common_subexpressions(code):
    """A value computed again in the same block while a variable still holds it is copied
    from that variable (value numbering, i.e. building the block's DAG)."""
    res = _start("common subexpressions", code)
    fg, blocks = _blocks(res.after)
    for b, lines in blocks:
        def rewrite(line, h, n):
            x = parse(line.instr)[1][0]
            what = expression(line.instr) or line.instr.split(":=")[1].strip()
            _set(res, line, f"{x} := {h}", f"{what} already in {h} (node {n})")
        _number_block(res.after, b, lines, rewrite)
    return res


def inline_expansion(code):
    """`x := call f, n` is replaced by the body of f (parameters become copies, `return v`
    becomes `x := v` and a jump to the end). Only for functions that call nothing (so no
    recursion) and have no local arrays. A function that is no longer called is removed."""
    res = _start("inline expansion", code)
    c = res.after
    procs = c.procedures()
    candidates = [f for f in c.functions()
                  if not any(parse(l.instr)[0] in ("call", "call_value") for l, p in zip(c.lines, procs) if p == f)
                  and not any(e.length for e in c.frames[f].entries.values())]
    count = Counter()
    i = 0
    while i < len(c.lines):
        form, p = parse(c.lines[i].instr)
        f, n = (p[1], int(p[2])) if form == "call_value" else (p[0], int(p[1])) if form == "call" else (None, 0)
        if f not in candidates or i < n or any(parse(c.lines[k].instr)[0] != "param" for k in range(i - n, i)):
            i += 1
            continue
        procs = c.procedures()
        count[f] += 1
        sfx = f"_{f}{count[f]}"
        frame = c.frames[f]
        rename = {name: name + sfx for name in frame.entries}
        body = [l for l, pr in zip(c.lines, procs) if pr == f]
        rename.update({lab: lab + sfx for l in body for lab in l.labels if lab != f})
        end = f"Lret{sfx}"
        main = c.frames[procs[i]]
        for e in frame.entries.values():
            main.entries[e.name + sfx] = tac.Entry(e.name + sfx, e.type, "temp", 4, main.size)
            main.size += 4
        params = sorted((e for e in frame.entries.values() if e.kind == "param"), key=lambda e: e.offset)
        new = []
        for e, k in zip(params, range(i - n, i)):
            arg = parse(c.lines[k].instr)[1][0]
            new.append(Line(c.lines[k].labels if k == i - n else [], f"{e.name}{sfx} := {arg}"))
            res.log.append(Change(c.lines[k].nr, f"argument -> parameter {e.name} of {f}", c.lines[k].instr, new[-1].instr))
        if n == 0:
            new.append(Line(c.lines[i].labels, None))

        def sub(text):
            import re
            return re.sub(r"\b[A-Za-z_]\w*\b", lambda m: rename.get(m[0], m[0]), text)

        for k, l in enumerate(body):
            labels = [rename[lab] for lab in l.labels if lab != f]
            bf, bp = parse(l.instr)
            if bf == "return":
                out = []
                if form == "call_value" and bp[0] is not None:
                    out.append(f"{p[0]} := {sub(bp[0])}")
                if k < len(body) - 1:
                    out.append(f"goto {end}")
                out = out or [None]
                new.append(Line(labels, out[0]))
                new += [Line([], o) for o in out[1:]]
            else:
                new.append(Line(labels, sub(l.instr)))
        res.log.append(Change(c.lines[i].nr, f"body of {f} ({len(body)} instructions) inlined", c.lines[i].instr, None))
        after = i + 1
        if after < len(c.lines):
            c.lines[after].labels.insert(0, end)
        else:
            c.end_labels.insert(0, end)
        c.lines[i - n:i + 1] = new
        i = i - n + len(new)
    c.compact()
    for f in candidates:
        procs = c.procedures()
        if any(_callee(l.instr) == f for l in c.lines):
            continue
        if count[f]:
            for l, pr in zip(c.lines, procs):
                if pr == f:
                    l.labels, l.instr = [], None
            del c.frames[f]
            res.log.append(Change(None, f"function {f} is no longer called: removed", None, None))
    c.compact()
    return res


def _callee(instr):
    form, p = parse(instr)
    return p[1] if form == "call_value" else p[0] if form == "call" else None


# --- loops -----------------------------------------------------------------------------------

def _preheader(fg, loop):
    """Index where code can be put in front of the loop: the header is entered from outside
    only by falling through from the block before it. None otherwise."""
    h = fg.block(loop.header)
    outside = [(f, kind) for f, t, kind in fg.edges if t == loop.header and f not in loop.blocks]
    if len(outside) == 1 and outside[0][1] == "fall-through":
        return h.start
    return None


def _loop_lines(fg, loop):
    return [i for b in loop.blocks for i in fg.block(b).indices()]


def _defs_in(code, fg, loop):
    proc = fg.block(loop.header).proc
    defs = Counter()
    for i in _loop_lines(fg, loop):
        ins = code.lines[i].instr
        if target(ins):
            defs[target(ins)] += 1
        if parse(ins)[0] in ("call", "call_value"):
            for v in _globals_in(code, proc):
                defs[v] += 2
    return defs


def _inner_first(fg):
    return sorted(fg.loops(), key=lambda lp: len(lp.blocks))


def loop_invariant_code_motion(code):
    """`x := a op b` moves in front of the loop if a and b are not changed in the loop, x is
    assigned only there, x is not read in the loop before it, and (if x is used after the
    loop) its block dominates every exit of the loop. Repeated until nothing moves."""
    res = _start("loop-invariant code motion", code)
    c = res.after
    moved = True
    while moved:
        moved = False
        fg = flow_graph(c)
        for loop in _inner_first(fg):
            pos = _preheader(fg, loop)
            if pos is None:
                continue
            proc = fg.block(loop.header).proc
            defs = _defs_in(c, fg, loop)
            lv = live_variables(c, proc)
            live_exit = set().union(*[lv.IN[s] for b in loop.exits for s in fg.succ(b) if s not in loop.blocks])
            dom = fg.dominators(proc)
            for i in _loop_lines(fg, loop):
                ins = c.lines[i].instr
                form, p = parse(ins)
                if form not in ("arith", "convert"):
                    continue
                x = p[0]
                if any(defs[v] for v in operands(ins)) or defs[x] != 1 or x in lv.IN[loop.header]:
                    continue
                if form == "arith" and p[2] == "/" and not tac.number(p[3]):
                    continue
                blk = fg.of_line(i).name
                if x in live_exit and not all(blk in dom[e] for e in loop.exits):
                    continue
                res.log.append(Change(c.lines[i].nr, f"invariant in loop {{{', '.join(loop.blocks)}}}: "
                                      f"moved in front of {loop.header}", ins, ins))
                c.lines[i].instr = None
                c.lines.insert(pos, Line([], ins, c.lines[i].nr))
                c.compact()
                moved = True
                break
            if moved:
                break
    return res


def _basic_ivs(code, fg, loop):
    """Basic induction variables: i -> (index of its only definition in the loop, step).
    Forms: `i := i + c`, `i := i - c`, or `t := i + c` followed by `i := t` in the same block."""
    defs = _defs_in(code, fg, loop)
    result = {}
    for b in loop.blocks:
        idx = list(fg.block(b).indices())
        for k, i in enumerate(idx):
            form, p = parse(code.lines[i].instr)
            v = target(code.lines[i].instr)
            if not v or defs[v] != 1:
                continue
            expr = None
            if form == "arith":
                expr = p
            elif form == "copy" and is_var(p[1]):
                for j in reversed(idx[:k]):
                    f2, p2 = parse(code.lines[j].instr)
                    if target(code.lines[j].instr) == v:
                        break
                    if target(code.lines[j].instr) == p[1]:
                        expr = p2 if f2 == "arith" else None
                        break
            if expr and expr[1] == v and expr[2] in "+-" and isinstance(tac.number(expr[3]), int):
                result[v] = (i, tac.number(expr[3]) * (1 if expr[2] == "+" else -1))
    return result


def induction_variables(code):
    """Strength reduction in loops: for a basic induction variable i (i += c once per pass)
    every `x := k * i` becomes `x := s`, where s := k * i is computed in front of the loop and
    s += k * c right after i changes. Typical: the byte offset 4 * j of an array index."""
    res = _start("induction variables", code)
    c = res.after
    done = True
    while done:
        done = False
        fg = flow_graph(c)
        for loop in _inner_first(fg):
            pos = _preheader(fg, loop)
            if pos is None:
                continue
            ivs = _basic_ivs(c, fg, loop)
            defs = _defs_in(c, fg, loop)
            groups = {}
            for i in _loop_lines(fg, loop):
                form, p = parse(c.lines[i].instr)
                if form != "arith" or p[2] != "*":
                    continue
                for iv, k in ((p[1], p[3]), (p[3], p[1])):
                    if iv in ivs and (is_const(k) or (is_var(k) and not defs[k] and ivs[iv][1] == 1)):
                        groups.setdefault((iv, k, f"{p[1]} * {p[3]}"), []).append(i)
                        break
            if not groups:
                continue
            (iv, k, expr), lines = next(iter(groups.items()))
            d, step = ivs[iv]
            s = c.new_temp()
            if is_const(k):
                inc = tac.number(k) * step
                update = f"{s} := {s} + {inc}" if inc >= 0 else f"{s} := {s} - {-inc}"
            else:
                update = f"{s} := {s} + {k}"
            for i in lines:
                x = parse(c.lines[i].instr)[1][0]
                res.log.append(Change(c.lines[i].nr, f"{expr} with induction variable {iv} (step {step}) is {s}",
                                      c.lines[i].instr, f"{x} := {s}"))
                c.lines[i].instr = f"{x} := {s}"
            res.log.append(Change(None, f"{s} grows with {iv}", None, update))
            c.lines.insert(d + 1, Line([], update))
            res.log.append(Change(None, f"{s} starts as {expr} in front of loop {loop.header}", None, f"{s} := {expr}"))
            c.lines.insert(pos, Line([], f"{s} := {expr}"))
            done = True
            break
    return res


def loop_unrolling(code, max_passes=8):
    """A loop `while (i cop C)` whose counter starts with a known constant and changes by a
    constant step runs a known number of times; if that is at most max_passes, the loop is
    replaced by that many copies of its body (labels inside renamed per copy)."""
    res = _start("loop unrolling", code)
    c = res.after
    fg = flow_graph(c)
    for loop in fg.loops():
        H = fg.block(loop.header)
        pos = _preheader(fg, loop)
        last = c.lines[H.end - 1].instr
        form, p = parse(last)
        if pos is None or form != "if" or H.end >= len(c.lines):
            continue
        g_form, g_p = parse(c.lines[H.end].instr)        # `goto exit` right after the test
        if g_form != "goto" or fg.of_line(H.end).name in loop.blocks:
            continue
        body = [b for b in loop.blocks if b != loop.header]
        b_start, b_end = fg.block(body[0]).start, fg.block(body[-1]).end
        if c.label_index()[p[3]] != b_start or b_start != H.end + 1 \
                or [b.name for b in fg.blocks if b_start <= b.start < b_end] != body:
            continue
        back = c.lines[b_end - 1].instr
        hlabels = c.lines[H.start].labels
        if parse(back)[0] != "goto" or parse(back)[1][0] not in hlabels:
            continue
        ivs = _basic_ivs(c, fg, loop)
        iv, bound, flip = (p[0], p[2], False) if p[0] in ivs and is_const(p[2]) else \
                          (p[2], p[0], True) if p[2] in ivs and is_const(p[0]) else (None, None, None)
        if iv is None or any(target(c.lines[i].instr) == iv for i in H.indices()):
            continue
        pre = fg.of_line(pos - 1)
        start = None
        for i in pre.indices():
            f2, p2 = parse(c.lines[i].instr)
            if target(c.lines[i].instr) == iv:
                start = tac.number(p2[1]) if f2 == "copy" and is_const(p2[1]) else None
        if not isinstance(start, int):
            continue
        cond = tac.COMPARE[p[1]]
        v, trips = start, 0
        while (cond(tac.number(bound), v) if flip else cond(v, tac.number(bound))) and trips <= max_passes:
            v += ivs[iv][1]
            trips += 1
        if trips > max_passes:
            continue
        inner = {lab for i in range(b_start, b_end) for lab in c.lines[i].labels}
        head = [c.lines[i].instr for i in range(H.start, H.end - 1)]
        new = []
        for k in range(1, trips + 1):
            ren = {lab: f"{lab}_{k}" for lab in inner}
            new += [Line([], h) for h in head]
            for i in range(b_start, b_end - 1):
                ins = c.lines[i].instr
                for t in bound_targets(ins):
                    if t in ren:
                        ins = ins.replace(f"goto {t}", f"goto {ren[t]}")
                new.append(Line([ren[l] for l in c.lines[i].labels], ins))
        new += [Line([], h) for h in head]
        jumped = {t for l in new for t in bound_targets(l.instr)}
        for l in new:
            l.labels = [lab for lab in l.labels if lab in jumped]
        exit_label = g_p[0]
        if c.label_index()[exit_label] != b_end:
            new.append(Line([], f"goto {exit_label}"))
        res.log.append(Change(c.lines[H.start].nr, f"loop {{{', '.join(loop.blocks)}}}: {iv} runs from {start} "
                              f"while {last.split(' goto')[0][3:]}: {trips} passes, body copied {trips} times",
                              last, None))
        if not new:
            new = [Line([], f"goto {exit_label}")]
        new[0].labels = [l for l in hlabels if l not in {parse(back)[1][0]}] + new[0].labels
        c.lines[H.start:b_end] = new
        c.compact()
        break
    return res


def bound_targets(instr):
    form, p = parse(instr)
    return [p[0]] if form == "goto" else [p[3]] if form == "if" else []


# --- global -----------------------------------------------------------------------------------

def dead_code_elimination(code, at_exit=None):
    """Removes blocks that can never run and assignments whose value is never read (live
    variables: the target is dead right after the assignment). Repeated until nothing
    changes, because removing one assignment can make the ones feeding it dead."""
    res = _start("dead code elimination", code)
    c = res.after
    while True:
        fg = flow_graph(c)
        changed = False
        for proc in fg.procs():
            seen = fg.reachable(proc)
            for b in fg.blocks_of(proc):
                if b not in seen:
                    for i in fg.block(b).indices():
                        res.log.append(Change(c.lines[i].nr, f"block {b} is unreachable", c.lines[i].instr, None))
                        c.lines[i].labels, c.lines[i].instr = [], None
                        changed = True
        if changed:
            c.compact()
            continue
        dead = dead_assignments(c, at_exit)
        for i, v in dead:
            res.log.append(Change(c.lines[i].nr, f"{v} is dead after this line", c.lines[i].instr, None))
            c.lines[i].instr = None
        if not dead:
            return res
        c.compact()


def code_hoisting(code):
    """An expression that is very busy at the end of a branching block (every path computes
    it before its operands change) is computed once in that block, before the jump; the
    first computation on every path copies the result."""
    res = _start("code hoisting", code)
    c = res.after
    while True:
        fg = flow_graph(c)
        found = None
        for proc in fg.procs():
            vb = very_busy_expressions(c, proc)
            for b in vb.blocks:
                blk = fg.block(b)
                if parse(c.lines[blk.end - 1].instr)[0] != "if":
                    continue
                for e in sorted(vb.OUT[b]):
                    sites, ok, seen = [], True, set()

                    def walk(name):
                        nonlocal ok
                        if name in seen or len(fg.pred(name)) != 1:
                            ok = False
                            return
                        seen.add(name)
                        for i in fg.block(name).indices():
                            if expression(c.lines[i].instr) == e:
                                sites.append(i)
                                return
                        if not fg.succ(name):
                            ok = False
                        for s in fg.succ(name):
                            walk(s)

                    for s in fg.succ(b):
                        walk(s)
                    if ok and len(sites) >= 2:
                        found = (b, blk, e, sites)
                        break
                if found:
                    break
            if found:
                break
        if not found:
            return res
        b, blk, e, sites = found
        h = c.new_temp()
        for i in sites:
            x = parse(c.lines[i].instr)[1][0]
            res.log.append(Change(c.lines[i].nr, f"{e} is very busy at the end of {b}: computed there once",
                                  c.lines[i].instr, f"{x} := {h}"))
            c.lines[i].instr = f"{x} := {h}"
        res.log.append(Change(None, f"{e} moved up into {b}, before its jump", None, f"{h} := {e}"))
        # before the block's final jump; if the jump is the block's first instruction its
        # labels (e.g. the function name) move to the new instruction, so it stays in the block
        jump = c.lines[blk.end - 1]
        c.lines.insert(blk.end - 1, Line(jump.labels, f"{h} := {e}"))
        jump.labels = []


# --- running several ------------------------------------------------------------------------

LOCAL = [constant_propagation, constant_folding, copy_propagation, algebraic_simplification,
         strength_reduction, common_subexpressions]
LOOP = [loop_invariant_code_motion, induction_variables, loop_unrolling]
GLOBAL = [dead_code_elimination, code_hoisting]
ALL = LOCAL + [inline_expansion] + LOOP + GLOBAL


def pipeline(code, passes=None, max_rounds=10):
    """Applies the passes (default: local ones + dead code elimination) again and again until
    a whole round changes nothing. Returns the list of Results that changed something."""
    passes = passes or LOCAL + [dead_code_elimination]
    steps = []
    for _ in range(max_rounds):
        changed = False
        for opt in passes:
            r = opt(code)
            if r.log:
                steps.append(r)
                code = r.after
                changed = True
        if not changed:
            break
    return steps


def main():
    code = load(sys.argv[1])
    which = sys.argv[2] if len(sys.argv) > 2 else "all"
    print(code.numbered())
    if which == "pipeline":
        steps = pipeline(code)
        for r in steps:
            print()
            print(r.report())
        final = steps[-1].after if steps else code
        print()
        print(final.listing())
        print("same behaviour:", code.run() == final.run())
        return
    for opt in ALL:
        if which in ("all", opt.__name__):
            r = opt(code)
            print()
            print(r.report())
            if r.log and which != "all":
                print(r.side_by_side())
            print("same behaviour:", check(r))


if __name__ == "__main__":
    main()
