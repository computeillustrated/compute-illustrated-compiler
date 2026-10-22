"""Basic blocks, flow graphs and loops for three-address code.

Reads the output of `calc -s -t` (frame tables + instructions), cuts it into basic blocks by
the leader rules, connects the blocks to a flow graph and finds loops (back edges via
dominators, natural loops). The `Code` class is also the program representation the
optimizer works on: it can be printed back as runnable 3AC (frame tables included, new
temporaries get a slot) and executed with the 3AC machine tac.py from the sibling folder.

Usage:  python blocks.py sortieren          leaders, blocks, edges, loops
        python blocks.py path/to/prog.tac
"""
import copy
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
# tac.py (3AC parser and machine) lives in a sibling folder, together with its programs/
TAC_DIR = next(p for p in sorted(HERE.parent.iterdir()) if (p / "tac.py").is_file())
sys.path.insert(0, str(TAC_DIR))
import tac  # noqa: E402

PROGRAM_DIRS = [HERE / "programs", TAC_DIR / "programs"]


# --- Instructions -------------------------------------------------------------------------

def parse(instr):
    """(form, parts) of an instruction, forms as in tac.py ("arith", "if", ...)."""
    return tac.parse_instruction(instr)


def is_const(arg):
    return tac.number(arg) is not None


def is_var(arg):
    return arg is not None and not is_const(arg)


def build(form, p):
    """Instruction text from form and parts (inverse of parse)."""
    return {
        "goto": lambda: f"goto {p[0]}",
        "if": lambda: f"if {p[0]} {p[1]} {p[2]} goto {p[3]}",
        "call_value": lambda: f"{p[0]} := call {p[1]}, {p[2]}",
        "call": lambda: f"call {p[0]}, {p[1]}",
        "param": lambda: f"param {p[0]}",
        "return": lambda: "return" if p[0] is None else f"return {p[0]}",
        "print": lambda: f"print {p[0]}",
        "convert": lambda: f"{p[0]} := inttofloat {p[1]}",
        "array_read": lambda: f"{p[0]} := {p[1]}[{p[2]}]",
        "array_write": lambda: f"{p[0]}[{p[1]}] := {p[2]}",
        "arith": lambda: f"{p[0]} := {p[1]} {p[2]} {p[3]}",
        "copy": lambda: f"{p[0]} := {p[1]}",
    }[form]()


# operand positions (indices into parts) that are read as values
READ_POS = {"arith": (1, 3), "copy": (1,), "convert": (1,), "array_read": (2,),
            "array_write": (1, 2), "if": (0, 2), "param": (0,), "return": (0,), "print": (0,)}


def target(instr):
    """The variable an instruction defines completely, or None (array stores are no
    complete definition)."""
    form, p = parse(instr)
    if form in ("arith", "copy", "convert", "array_read", "call_value"):
        return p[0]
    return None


def operands(instr):
    """Variables read as values (no constants). Array reads/stores also read the array."""
    form, p = parse(instr)
    used = [p[i] for i in READ_POS.get(form, ()) if is_var(p[i])]
    if form == "array_read":
        used.insert(0, p[1])
    if form == "array_write":
        used.insert(0, p[0])
    return used


def replace_operands(instr, mapping):
    """Replaces read operands (not targets, not array names) by mapping[name]."""
    form, p = parse(instr)
    p = list(p)
    for i in READ_POS.get(form, ()):
        if p[i] is not None and p[i] in mapping:
            p[i] = mapping[p[i]]
    return build(form, p)


def expression(instr):
    """"a op b" for `x := a op b`, else None."""
    form, p = parse(instr)
    return f"{p[1]} {p[2]} {p[3]}" if form == "arith" else None


def jump_targets(instr):
    form, p = parse(instr)
    return [p[0]] if form == "goto" else [p[3]] if form == "if" else []


def ends_block(instr):
    return parse(instr)[0] in ("goto", "if", "return")


def falls_through(instr):
    return parse(instr)[0] not in ("goto", "return")


# --- Program ------------------------------------------------------------------------------

@dataclass
class Line:
    labels: list
    instr: str
    nr: int = None              # line number in the original program (None = inserted)


class Code:
    """A 3AC program: frame tables plus a list of lines (labels + one instruction)."""

    def __init__(self, frames, lines, end_labels=None):
        self.frames = frames            # name -> tac.Frame
        self.lines = lines
        self.end_labels = end_labels or []

    @classmethod
    def parse(cls, text):
        frames = tac.read_program(text).frames
        lines, pending = [], []
        for row in text.splitlines():
            if not row.strip() or row.startswith("#"):
                continue
            if row.rstrip().endswith(":") and not row.startswith(" "):
                pending.append(row.strip()[:-1])
            else:
                parse(row.strip())          # fail early on unknown instructions
                lines.append(Line(pending, row.strip(), len(lines) + 1))
                pending = []
        return cls(frames, lines, pending)

    def copy(self):
        return copy.deepcopy(self)

    @property
    def instrs(self):
        return [l.instr for l in self.lines]

    def label_index(self):
        """label -> index of the instruction it marks (len(lines) for a label at the end)."""
        idx = {lab: i for i, l in enumerate(self.lines) for lab in l.labels}
        idx.update({lab: len(self.lines) for lab in self.end_labels})
        return idx

    def functions(self):
        return [f for f in self.frames if f != "main"]

    def procedures(self):
        """Procedure of every line: lines before the first function label belong to main
        (`goto main` is the first instruction of the program)."""
        current, result = "main", []
        for l in self.lines:
            for lab in l.labels:
                if lab in self.frames:
                    current = lab
            result.append(current)
        return result

    def globals_(self):
        """Variables of main (kind var): visible in functions, reported after the run."""
        return {e.name for e in self.frames["main"].entries.values() if e.kind == "var"}

    def is_global(self, name, proc):
        return (proc == "main" or name not in self.frames[proc].entries) and name in self.globals_()

    def compact(self):
        """Removes lines whose instr is None; their labels move to the next instruction."""
        lines, pending = [], []
        for l in self.lines:
            if l.instr is None:
                pending += l.labels
            else:
                lines.append(Line(pending + l.labels, l.instr, l.nr))
                pending = []
        self.lines, self.end_labels = lines, pending + self.end_labels
        return self

    def new_temp(self):
        """A temporary name not used anywhere yet (t28 after t27)."""
        used = set()
        for f in self.frames.values():
            used |= set(f.entries)
        for l in self.lines:
            used |= set(re.findall(r"\bt\d+\b", l.instr))
        n = max([int(u[1:]) for u in used if re.fullmatch(r"t\d+", u)] + [0]) + 1
        return f"t{n}"

    def listing(self):
        """Instructions with labels, in the format of `calc -t`."""
        out = []
        for l in self.lines:
            out += [f"{lab}:" for lab in l.labels] + [f"    {l.instr}"]
        out += [f"{lab}:" for lab in self.end_labels]
        return "\n".join(out) + "\n"

    def numbered(self):
        """Listing with line numbers (1, 2, ...) as used in all logs."""
        out = []
        for i, l in enumerate(self.lines, 1):
            out += [f"{lab}:" for lab in l.labels] + [f"{i:4}  {l.instr}"]
        out += [f"{lab}:" for lab in self.end_labels]
        return "\n".join(out)

    def text(self):
        """Runnable 3AC with frame tables; names not in any table get a temp slot in the
        frame of their procedure (type int, float if computed from a float)."""
        frames = copy.deepcopy(self.frames)
        types = {}
        for proc, l in zip(self.procedures(), self.lines):
            local = frames[proc].entries

            def type_of(arg):
                if is_const(arg):
                    return tac.type_of(tac.number(arg))
                e = local.get(arg) or frames["main"].entries.get(arg)
                return e.type if e else types.get((proc, arg), "int")

            form, p = parse(l.instr)
            names = operands(l.instr) + ([target(l.instr)] if target(l.instr) else [])
            for name in names:
                if name in local or name in frames["main"].entries:
                    continue
                if name == target(l.instr):
                    if form == "convert":
                        typ = "float"
                    elif form in ("arith", "copy"):
                        typ = type_of(p[1])
                    elif form == "array_read":
                        typ = type_of(p[1])
                    else:
                        typ = "int"
                else:
                    typ = types.get((proc, name), "int")
                types[(proc, name)] = typ
                fr = frames[proc]
                fr.entries[name] = tac.Entry(name, typ, "temp", 4, fr.size)
                fr.size += 4
        head = []
        for fr in frames.values():
            head.append(f"# frame {fr.name}, depth {fr.depth}, size {fr.size}")
            head.append("#   name     type      kind   size offset")
            for e in fr.entries.values():
                typ = f"{e.type}[{e.length}]" if e.length else e.type
                head.append(f"#   {e.name:<8} {typ:<9} {e.kind:<6} {e.size:>4} {e.offset:>6}")
        return "\n".join(head) + "\n" + self.listing()

    def run(self):
        """Executes the code with tac.py: (printed lines, final values of main's variables)."""
        m = tac.run(self.text())
        return m.output, m.global_values()


def load(name):
    """Code of a program by name (`sortieren`) or path (`x.tac`)."""
    path = Path(name)
    if not path.exists():
        for d in PROGRAM_DIRS:
            if (d / f"{name}.tac").exists():
                path = d / f"{name}.tac"
                break
    return Code.parse(path.read_text())


# --- Leaders and blocks -------------------------------------------------------------------

def leaders(code):
    """Leader index -> reasons (1-based line numbers in the reasons)."""
    instrs, labels = code.instrs, code.label_index()
    reasons = {}

    def add(i, why):
        if i < len(instrs):
            reasons.setdefault(i, []).append(why)

    add(0, "first instruction of the program")
    callers = {}
    for i, ins in enumerate(instrs):
        form, p = parse(ins)
        if form in ("call", "call_value"):
            callers.setdefault(p[1] if form == "call_value" else p[0], []).append(i + 1)
    for i, l in enumerate(code.lines):
        for lab in l.labels:
            if lab in code.functions():
                at = callers.get(lab, [])
                where = f"called in line{'s' if len(at) > 1 else ''} {', '.join(map(str, at))}" if at else "never called"
                add(i, f"first instruction of function {lab} ({where})")
    for i, ins in enumerate(instrs):
        for lab in jump_targets(ins):
            add(labels[lab], f"target of {parse(ins)[0]} in line {i + 1}")
        if ends_block(ins):
            add(i + 1, f"follows the {parse(ins)[0]} in line {i + 1}")
    return dict(sorted(reasons.items()))


@dataclass
class Block:
    name: str
    start: int                  # index of the first instruction
    end: int                    # index after the last instruction
    proc: str
    reasons: list

    def indices(self):
        return range(self.start, self.end)


@dataclass
class Loop:
    header: str
    back_edges: list            # [(tail, header)]
    blocks: list                # block names, in text order
    exits: list                 # blocks of the loop with a successor outside


@dataclass
class FlowGraph:
    code: Code
    blocks: list
    edges: list                 # (from, to, "jump" | "fall-through")
    entry: dict                 # procedure -> first block
    exits: dict                 # procedure -> blocks that leave the procedure

    def block(self, name):
        return next(b for b in self.blocks if b.name == name)

    def of_line(self, i):
        return next(b for b in self.blocks if b.start <= i < b.end)

    def succ(self, name):
        return [t for f, t, _ in self.edges if f == name]

    def pred(self, name):
        return [f for f, t, _ in self.edges if t == name]

    def procs(self):
        return list(self.entry)

    def blocks_of(self, proc):
        return [b.name for b in self.blocks if b.proc == proc]

    def instrs(self, name):
        b = self.block(name)
        return [self.code.lines[i].instr for i in b.indices()]

    def reachable(self, proc):
        seen, todo = set(), [self.entry[proc]]
        while todo:
            b = todo.pop()
            if b not in seen:
                seen.add(b)
                todo += self.succ(b)
        return seen

    # --- dominators and loops -------------------------------------------------------------
    def dominators(self, proc):
        """Block -> set of blocks dominating it (iterative, only reachable blocks)."""
        nodes = [b for b in self.blocks_of(proc) if b in self.reachable(proc)]
        start = self.entry[proc]
        dom = {b: set(nodes) for b in nodes}
        dom[start] = {start}
        changed = True
        while changed:
            changed = False
            for b in nodes:
                if b == start:
                    continue
                preds = [dom[p] for p in self.pred(b) if p in dom]
                new = {b} | (set.intersection(*preds) if preds else set())
                if new != dom[b]:
                    dom[b], changed = new, True
        return dom

    def loops(self, proc=None):
        """Natural loops: for every back edge n -> h (h dominates n) the blocks that reach n
        without passing h, plus h. Back edges with the same header form one loop."""
        result = []
        for pr in ([proc] if proc else self.procs()):
            dom = self.dominators(pr)
            back = [(f, t) for f, t, _ in self.edges if f in dom and t in dom[f]]
            for h in dict.fromkeys(t for _, t in back):
                body = {h}
                tails = [f for f, t in back if t == h]
                todo = list(tails)
                while todo:
                    b = todo.pop()
                    if b not in body:
                        body.add(b)
                        todo += self.pred(b)
                names = [b.name for b in self.blocks if b.name in body]
                exits = [b for b in names if any(s not in body for s in self.succ(b))]
                result.append(Loop(h, [(t, h) for t in tails], names, exits))
        return result

    def describe(self):
        code, out = self.code, []
        out.append("Leaders:")
        for i, why in leaders(code).items():
            out.append(f"  line {i + 1:3}  {code.lines[i].instr:<24} " + "; ".join(why))
        out.append("Blocks:")
        for b in self.blocks:
            out.append(f"  {b.name} ({b.proc}, lines {b.start + 1}-{b.end})")
            for i in b.indices():
                l = code.lines[i]
                lab = ", ".join(l.labels)
                out.append(f"      {i + 1:3}  {(lab + ':') if lab else '':<6} {l.instr}")
        out.append("Edges:")
        for f, t, kind in self.edges:
            out.append(f"  {f} -> {t}  ({kind})")
        for p in self.procs():
            out.append(f"Entry of {p}: {self.entry[p]}, exits: {', '.join(self.exits[p]) or '-'}")
        for lp in self.loops():
            back = ", ".join(f"{a} -> {b}" for a, b in lp.back_edges)
            out.append(f"Loop with header {lp.header}: back edge {back}, blocks "
                       f"{{{', '.join(lp.blocks)}}}, exits {', '.join(lp.exits)}")
        return "\n".join(out)


def flow_graph(code):
    """Basic blocks and flow graph of a program."""
    instrs, labels, procs = code.instrs, code.label_index(), code.procedures()
    lead = leaders(code)
    starts = sorted(lead) + [len(instrs)]
    blocks = [Block(f"B{k + 1}", s, e, procs[s], lead[s]) for k, (s, e) in enumerate(zip(starts, starts[1:]))]
    by_start = {b.start: b.name for b in blocks}
    edges, exits = [], {}
    entry = {}
    for b in blocks:
        entry.setdefault(b.proc, b.name)
        exits.setdefault(b.proc, [])
        last = instrs[b.end - 1]
        for lab in jump_targets(last):
            if labels[lab] < len(instrs):
                edges.append((b.name, by_start[labels[lab]], "jump"))
            elif b.name not in exits[b.proc]:
                exits[b.proc].append(b.name)
        if falls_through(last):
            if b.end < len(instrs) and procs[b.end] == b.proc:
                edges.append((b.name, by_start[b.end], "fall-through"))
            elif b.name not in exits[b.proc]:
                exits[b.proc].append(b.name)
        if parse(last)[0] == "return" and b.name not in exits[b.proc]:
            exits[b.proc].append(b.name)
    return FlowGraph(code, blocks, edges, entry, exits)


def main():
    code = load(sys.argv[1])
    print(code.numbered())
    print()
    print(flow_graph(code).describe())


if __name__ == "__main__":
    main()
