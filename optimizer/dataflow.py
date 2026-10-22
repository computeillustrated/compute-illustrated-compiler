"""Data-flow analysis on the flow graph: gen, kill, in, out, solved round by round.

Four analyses, one per combination of direction and meet:
    reaching definitions    forward,  any (union)         which definitions reach a block
    available expressions   forward,  all (intersection)  which a op b are already computed
    live variables          backward, any (union)         whose value may still be needed
    very busy expressions   backward, all (intersection)  which a op b every path computes

The solver starts from the boundary (entry block for forward, exit blocks for backward)
and recomputes every block in order (text order forward, reverse text order backward,
new values are used at once) until a whole round changes nothing. Every round is kept as a
table, so the iteration can be shown step by step.

Calls: a called function may read and write the variables of main (globals). A call
therefore counts as a use of every global (live variables) and kills every expression
with a global operand (available / very busy expressions). Array stores are not
definitions (they change one element only).

Usage:  python dataflow.py sortieren [reaching|available|live|busy] [procedure]
"""
import re
import sys
from dataclasses import dataclass, field

from blocks import flow_graph, load, operands, parse, target, expression, is_var

def natural(text):
    """Sort key: t9 before t10."""
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", text)]


PURE = ("arith", "copy", "convert", "array_read")   # no effect besides the target


@dataclass
class Analysis:
    name: str
    direction: str              # "forward" | "backward"
    meet: str                   # "any" | "all"
    proc: str
    blocks: list                # block names in text order
    gen: dict
    kill: dict
    universe: set
    boundary: set
    rounds: list = field(default_factory=list)   # [{"in": {...}, "out": {...}, "changed": [...]}]

    @property
    def IN(self):
        return self.rounds[-1]["in"]

    @property
    def OUT(self):
        return self.rounds[-1]["out"]

    def fmt(self, s):
        if self.name == "reaching definitions":
            return "{" + ", ".join(map(str, sorted(s))) + "}"
        return "{" + ", ".join(sorted(s, key=natural)) + "}"

    def table(self, r=-1, sets=("in", "out")):
        """One round as a text table (round 0 = initialisation)."""
        rnd = self.rounds[r]
        rows = [f"{'Block':<6} {'gen':<24} {'kill':<24} " + " ".join(f"{s:<28}" for s in sets)]
        for b in self.blocks:
            rows.append(f"{b:<6} {self.fmt(self.gen[b]):<24} {self.fmt(self.kill[b]):<24} "
                        + " ".join(f"{self.fmt(rnd[s][b]):<28}" for s in sets))
        return "\n".join(rows)

    def protocol(self):
        out = [f"{self.name} ({self.direction}-{self.meet}) in {self.proc}: "
               f"{len(self.rounds) - 1} rounds, round {len(self.rounds) - 1} changes nothing"]
        for k, rnd in enumerate(self.rounds):
            head = "initialisation" if k == 0 else f"round {k}"
            changed = ", ".join(rnd["changed"]) or "nothing changed"
            out.append(f"--- {head}: {changed}")
            out.append(self.table(k))
        return "\n".join(out)


def solve(a, fg):
    """Iterates the equations until nothing changes; fills a.rounds."""
    fwd = a.direction == "forward"
    order = a.blocks if fwd else list(reversed(a.blocks))
    start = {fg.entry[a.proc]} if fwd else set(fg.exits[a.proc])
    IN, OUT = {}, {}
    full = set(a.universe)
    for b in a.blocks:
        if fwd:
            IN[b] = set(a.boundary) if b in start else set() if a.meet == "any" else set(full)
            OUT[b] = a.gen[b] | (IN[b] - a.kill[b])
        else:
            OUT[b] = set(a.boundary) if b in start else set() if a.meet == "any" else set(full)
            IN[b] = a.gen[b] | (OUT[b] - a.kill[b])
    a.rounds = [{"in": {b: set(IN[b]) for b in a.blocks}, "out": {b: set(OUT[b]) for b in a.blocks},
                 "changed": list(a.blocks)}]
    blockset = set(a.blocks)
    while True:
        changed = []
        for b in order:
            if fwd:
                srcs = [OUT[p] for p in fg.pred(b) if p in blockset]
                if b in start:
                    srcs.append(a.boundary)
                new_in = (set().union(*srcs) if a.meet == "any" else set.intersection(*map(set, srcs))) if srcs else set(full if a.meet == "all" else ())
                new_out = a.gen[b] | (new_in - a.kill[b])
            else:
                srcs = [IN[s] for s in fg.succ(b) if s in blockset]
                if b in start or not srcs:
                    srcs.append(a.boundary)
                new_out = set().union(*srcs) if a.meet == "any" else set.intersection(*map(set, srcs))
                new_in = a.gen[b] | (new_out - a.kill[b])
            if new_in != IN[b] or new_out != OUT[b]:
                changed.append(b)
            IN[b], OUT[b] = new_in, new_out
        a.rounds.append({"in": {b: set(IN[b]) for b in a.blocks}, "out": {b: set(OUT[b]) for b in a.blocks},
                         "changed": changed})
        if not changed:
            return a


# --- helpers -----------------------------------------------------------------------------

def _effects(code, proc, instr):
    """(read variables, defined variables) of an instruction, calls included."""
    form, p = parse(instr)
    reads = operands(instr)
    defs = [target(instr)] if target(instr) else []
    if form in ("call", "call_value"):
        glob = sorted(v for v in code.globals_() if code.is_global(v, proc))
        reads = reads + glob
        defs = defs + glob          # may be changed by the callee
    return reads, defs


def _expr_operands(e):
    a, _, b = e.split()
    return {x for x in (a, b) if is_var(x)}


def _setup(code, proc):
    fg = flow_graph(code)
    blocks = fg.blocks_of(proc)
    return fg, blocks


# --- the four analyses ---------------------------------------------------------------------

def reaching_definitions(code, proc="main", variables_only=False):
    """Definitions are line numbers (1-based). variables_only: ignore temporaries."""
    fg, blocks = _setup(code, proc)
    frame = code.frames[proc].entries

    def counts(v):
        e = frame.get(v) or code.frames["main"].entries.get(v)
        return not variables_only or (e is not None and e.kind != "temp")

    defs = {}                                    # line -> variable
    for b in blocks:
        for i in fg.block(b).indices():
            t = target(code.lines[i].instr)
            if t and counts(t):
                defs[i + 1] = t
    gen, kill = {}, {}
    for b in blocks:
        last = {}
        for i in fg.block(b).indices():
            if (i + 1) in defs:
                last[defs[i + 1]] = i + 1
        gen[b] = set(last.values())
        own = set(range(fg.block(b).start + 1, fg.block(b).end + 1))
        kill[b] = {d for d, v in defs.items() if v in last and d not in own}
    a = Analysis("reaching definitions", "forward", "any", proc, blocks, gen, kill, set(defs), set())
    a.definitions = defs
    return solve(a, fg)


def _expressions(code, fg, blocks):
    return {expression(code.lines[i].instr) for b in blocks for i in fg.block(b).indices()
            if expression(code.lines[i].instr)}


def available_expressions(code, proc="main"):
    fg, blocks = _setup(code, proc)
    U = _expressions(code, fg, blocks)
    gen, kill = {}, {}
    for b in blocks:
        g, defined = set(), set()
        for i in fg.block(b).indices():
            ins = code.lines[i].instr
            _, ds = _effects(code, proc, ins)
            if expression(ins):
                g.add(expression(ins))
            for x in ds:
                defined.add(x)
                g = {e for e in g if x not in _expr_operands(e)}
        gen[b] = g
        kill[b] = {e for e in U if _expr_operands(e) & defined} - g
    return solve(Analysis("available expressions", "forward", "all", proc, blocks, gen, kill, U, set()), fg)


def default_at_exit(code, proc):
    """Variables live at the end of a procedure: the globals (main's variables are read
    after the run and may be read by later code after a function returns)."""
    return set(code.globals_())


def live_variables(code, proc="main", at_exit=None):
    fg, blocks = _setup(code, proc)
    gen, kill = {}, {}
    for b in blocks:
        g, k = set(), set()
        for i in fg.block(b).indices():
            reads, ds = _effects(code, proc, code.lines[i].instr)
            g |= {v for v in reads if v not in k}
            if parse(code.lines[i].instr)[0] not in ("call", "call_value"):
                k |= set(ds)
            elif target(code.lines[i].instr):
                k.add(target(code.lines[i].instr))
        gen[b], kill[b] = g, k
    boundary = default_at_exit(code, proc) if at_exit is None else set(at_exit)
    U = set().union(*gen.values(), *kill.values(), boundary)
    return solve(Analysis("live variables", "backward", "any", proc, blocks, gen, kill, U, boundary), fg)


def very_busy_expressions(code, proc="main"):
    fg, blocks = _setup(code, proc)
    U = _expressions(code, fg, blocks)
    gen, kill = {}, {}
    for b in blocks:
        g, defined = set(), set()
        for i in fg.block(b).indices():
            ins = code.lines[i].instr
            e = expression(ins)
            if e and not (_expr_operands(e) & defined):
                g.add(e)
            defined |= set(_effects(code, proc, ins)[1])
        gen[b] = g
        kill[b] = {e for e in U if _expr_operands(e) & defined}
    return solve(Analysis("very busy expressions", "backward", "all", proc, blocks, gen, kill, U, set()), fg)


ANALYSES = {"reaching": reaching_definitions, "available": available_expressions,
            "live": live_variables, "busy": very_busy_expressions}


# --- application: dead code from live variables ------------------------------------------------

def live_after(code, proc="main", at_exit=None):
    """Line index -> variables live directly after that instruction."""
    lv = live_variables(code, proc, at_exit)
    fg = flow_graph(code)
    result = {}
    for b in lv.blocks:
        live = set(lv.OUT[b])
        for i in reversed(fg.block(b).indices()):
            result[i] = set(live)
            ins = code.lines[i].instr
            reads, ds = _effects(code, proc, ins)
            if target(ins):
                live.discard(target(ins))
            live |= set(reads)
    return result


def dead_assignments(code, at_exit=None):
    """[(line index, variable)] of assignments whose value nobody reads: the target is dead
    after the instruction and the instruction has no other effect."""
    dead = []
    procs = code.procedures()
    for proc in dict.fromkeys(procs):
        live = live_after(code, proc, at_exit if proc == "main" else None)
        for i, l in enumerate(code.lines):
            if procs[i] != proc or i not in live:
                continue
            t = target(l.instr)
            if t and parse(l.instr)[0] in PURE and t not in live[i]:
                dead.append((i, t))
    return dead


def main():
    code = load(sys.argv[1])
    which = sys.argv[2] if len(sys.argv) > 2 else "live"
    proc = sys.argv[3] if len(sys.argv) > 3 else "main"
    print(code.numbered())
    print()
    print(ANALYSES[which](code, proc).protocol())
    if which == "live":
        print("\nDead assignments:", ", ".join(f"line {i + 1} ({v})" for i, v in dead_assignments(code)) or "none")


if __name__ == "__main__":
    main()
