"""Code generation: three-address code -> assembler for a simple target machine.

Target machine
    n registers R0 … R(n-1) (choose n, e.g. 2 or 3), data memory addressed by variable name.
    Operands: register R1, constant #10, memory x, indexed memory a[R1] (byte offset in R1).

    LD  R, X        R := X            (X: constant, memory, register or a[S])
    ST  R, V        V := R            (V: memory or a[S])
    ADD R, X  SUB R, X  MUL R, X  DIV R, X      R := R op X
    FLT R           R := float(R)     (inttofloat)
    CMP R, X        compare R with X, then
    JLT L  JLE L  JGT L  JGE L  JEQ L  JNE L    jump if the comparison holds
    JMP L           jump
    PARAM X         argument for the next call
    CALL f, n       call f with n arguments; the result arrives in R0
    RET [X]         return (with result X)
    PRINT X         print the value of X
    Only produced by the peephole optimizer: INC R, DEC R, SHL R, #k, MOV #c, V.

Code generation per basic block, one three-address instruction at a time:
    register descriptor  Con(R): names whose current value is in R
    address descriptor   Pos(v): places where the current value of v is (registers and/or
                         its memory cell; a set, so a value that is still correct in memory
                         is not stored again)
    getreg(x)            1. x alone in R, no further use, not live at block end -> reuse R
                         2. otherwise a free register
                         3. otherwise free a register: STORE what still needs to be kept
    next use / liveness  used(v): v is read again in this block before being overwritten;
                         live(v): v is live at the end of the block (live-variable analysis
                         over the flow graph)
At the end of a block (before its jump) and before every call, values that are live and
only in a register are stored. Every block starts with empty registers.

Usage:  python codegen.py prog.tac [registers] [--log] [--naive]
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# tac.py (3AC parser and machine) lives in a sibling folder
TAC_DIR = next(p for p in sorted(Path(__file__).resolve().parents[1].iterdir()) if (p / "tac.py").is_file())
sys.path.insert(0, str(TAC_DIR))
import tac  # noqa: E402

OPCODE = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}
JUMP = {"<": "JLT", "<=": "JLE", ">": "JGT", ">=": "JGE", "==": "JEQ", "!=": "JNE"}
ENDS_BLOCK = ("goto", "if", "return")


def is_const(a):
    return tac.number(a) is not None


def reads(form, parts):
    """Names read by a 3AC instruction (constants excluded)."""
    if form == "arith":
        names = [parts[1], parts[3]]
    elif form in ("copy", "convert"):
        names = [parts[1]]
    elif form == "array_read":
        names = [parts[2]]                       # the array itself is never in a register
    elif form == "array_write":
        names = [parts[1], parts[2]]
    elif form == "if":
        names = [parts[0], parts[2]]
    elif form in ("param", "print"):
        names = [parts[0]]
    elif form == "return":
        names = [parts[0]] if parts[0] else []
    else:
        names = []
    return [n for n in names if not is_const(n)]


def writes(form, parts):
    return parts[0] if form in ("arith", "copy", "convert", "array_read", "call_value") else None


# --- blocks and liveness ---------------------------------------------------------------

@dataclass
class Block:
    nr: int
    start: int                 # index of the first instruction in programm.instructions
    end: int                   # one past the last
    function: str
    labels: list
    succ: list = field(default_factory=list)
    live_out: set = field(default_factory=set)


def split_blocks(p):
    """Leaders: first instruction, every labelled instruction, every instruction after a
    jump or return."""
    leaders = {0} | set(p.labels.values())
    for i, b in enumerate(p.instructions):
        if tac.parse_instruction(b)[0] in ENDS_BLOCK:
            leaders.add(i + 1)
    leaders = sorted(x for x in leaders if x < len(p.instructions))
    blocks, function = [], "main"
    for nr, s in enumerate(leaders):
        e = leaders[nr + 1] if nr + 1 < len(leaders) else len(p.instructions)
        labels = p.labels_before.get(s, [])
        for m in labels:
            if m in p.frames:
                function = m
        blocks.append(Block(nr, s, e, function, labels))
    first = {s: b.nr for b in blocks for s in [b.start]}
    for b in blocks:
        form, parts = tac.parse_instruction(p.instructions[b.end - 1])
        if form == "goto":
            b.succ = [first[p.labels[parts[0]]]]
        elif form == "if":
            b.succ = [first[p.labels[parts[3]]]] + ([b.nr + 1] if b.nr + 1 < len(blocks) else [])
        elif form != "return" and b.nr + 1 < len(blocks) and blocks[b.nr + 1].function == b.function:
            b.succ = [b.nr + 1]
    return blocks


def globals_of(p):
    return {n for n, e in p.frames["main"].entries.items() if e.kind == "var"}


def visible_globals(p, function):
    """Global variables a block of `function` can see (main's own vars, or the ones not
    hidden by a local of the same name)."""
    g = globals_of(p)
    return g if function == "main" else g - set(p.frames[function].entries)


def liveness(p, blocks):
    """Live-variable analysis (backwards, any path). At a block without successors the visible
    global variables are live (their final values matter); a call reads all of them."""
    use, defs = {}, {}
    for b in blocks:
        u, d = set(), set()
        for i in range(b.start, b.end):
            form, parts = tac.parse_instruction(p.instructions[i])
            r = set(reads(form, parts))
            if form in ("call", "call_value"):
                r |= visible_globals(p, b.function)
            u |= r - d
            if (w := writes(form, parts)) is not None:
                d.add(w)
        use[b.nr], defs[b.nr] = u, d
    live_in = {b.nr: set() for b in blocks}
    changed = True
    while changed:
        changed = False
        for b in reversed(blocks):
            out = set().union(*(live_in[s] for s in b.succ)) if b.succ else visible_globals(p, b.function)
            new_in = use[b.nr] | (out - defs[b.nr])
            if out != b.live_out or new_in != live_in[b.nr]:
                b.live_out, live_in[b.nr] = out, new_in
                changed = True
    return blocks


# --- code generation ---------------------------------------------------------------------

@dataclass
class Step:
    """Log entry for one three-address instruction."""
    tac: str
    code: list                 # generated assembler lines
    decisions: list            # getreg and friends, with reasons
    con: dict                  # register -> sorted names, after the instruction
    pos: dict                  # name -> sorted places, after the instruction
    block: int = 0


class BlockGen:
    """Translates one basic block. `instructions`: list of 3AC strings, `live_end`: names live
    at the end of the block."""

    def __init__(self, instructions, registers, live_end, flush_at_call=()):
        self.ins = instructions
        self.regs = [f"R{i}" for i in range(registers)]
        self.live_end = set(live_end)
        self.con = {r: set() for r in self.regs}
        self.pos = {}                            # name -> set of places; missing = only in memory
        self.code, self.log, self.i = [], [], 0
        self.flush_extra = set(flush_at_call)    # globals a call may read

    # descriptors
    def places(self, v):
        return self.pos.get(v, {v})

    def reg_of(self, v):
        rs = sorted(p for p in self.places(v) if p in self.con)
        return rs[0] if rs else None

    def used(self, v):
        """v is read again in this block before it is overwritten."""
        for b in self.ins[self.i + 1:]:
            form, parts = tac.parse_instruction(b)
            if v in reads(form, parts):
                return True
            if writes(form, parts) == v:
                return False
        return False

    def live(self, v):
        return v in self.live_end

    def needed(self, v):
        return self.used(v) or self.live(v)

    def addr(self, x):
        """Preferred operand: constant #c, a register holding x, else its memory cell."""
        if is_const(x):
            return "#" + x
        return self.reg_of(x) or x

    def emit(self, line):
        self.code.append(line)
        self.step_code.append(line)

    def store(self, r, v, why):
        self.emit(f"ST {r}, {v}")
        self.pos[v] = self.places(v) | {v}
        self.decisions.append(why)

    def forget_reg(self, r):
        for v in self.con[r]:
            self.pos[v] = self.places(v) - {r}
        self.con[r] = set()

    def getreg(self, x, avoid=()):
        """Choose a register for an operation on x. Returns R; may emit STOREs."""
        r = None if is_const(x) else self.reg_of(x)
        if r and r not in avoid and self.con[r] == {x} and not self.used(x) and not self.live(x):
            self.decisions.append(f"getreg({x}): {r} holds only {x}, no further use, not live -> reuse {r}")
            self.con[r] = set()                  # the value of x stays in r until it is overwritten
            return r
        for r in self.regs:
            if not self.con[r] and r not in avoid:
                why = f"{r} is free"
                if self.reg_of(x) and not is_const(x):
                    why += f" ({x} stays in {self.reg_of(x)}: " + (
                        "used again" if self.used(x) else "live at block end" if self.live(x) else "shared") + ")"
                self.decisions.append(f"getreg({x}): {why}")
                return r
        # 3. no free register: pick the one that needs the fewest STOREs; on a tie the one that
        # already holds x (saves the load), then the lowest number
        def cost(r):
            current = reads(*tac.parse_instruction(self.ins[self.i]))
            keep = [y for y in self.con[r] if (self.needed(y) or y in current) and self.places(y) == {r}]
            return (len(keep), 0 if x in self.con[r] else 1, self.regs.index(r)), keep
        r = min((reg for reg in self.regs if reg not in avoid), key=lambda reg: cost(reg)[0])
        keep = cost(r)[1]
        self.decisions.append(f"getreg({x}): no free register -> free {r} (holds "
                              + ", ".join(sorted(self.con[r])) + ")")
        for y in sorted(keep):
            self.store(r, y, f"  {y} is still needed and only in {r} -> ST {r}, {y}")
        if x in self.con[r] and not is_const(x):
            # value of x stays in r; other names leave it
            for y in self.con[r] - {x}:
                self.pos[y] = self.places(y) - {r}
            self.con[r] = set()
            self.pos[x] = self.places(x) | {r}
        else:
            self.forget_reg(r)
        return r

    def load(self, r, x):
        """Make sure the value of x is in r (step 2 of codegen)."""
        if not is_const(x) and r in self.places(x):
            self.decisions.append(f"{x} is already in {r}: no load")
            return
        self.emit(f"LD {r}, {self.addr(x)}")

    def clobber(self, r, keep=()):
        """r is overwritten: no other name has its value there any more."""
        for n, p in self.pos.items():
            if r in p and n not in keep:
                self.pos[n] = p - {r}

    def define(self, v, r, also=()):
        """v (and the names in also) now live only in r."""
        self.clobber(r, keep=also)
        for s in self.regs:
            if s != r:
                self.con[s].discard(v)
        self.con[r] = {v, *also}
        self.pos[v] = {r}
        for a in also:
            self.pos[a] = self.places(a) | {r}

    def drop_dead(self, *names):
        """Step 4: operands without further use and not live leave the registers."""
        for x in names:
            if is_const(x) or self.needed(x):
                continue
            for s in self.regs:
                if x in self.con[s]:
                    self.con[s].discard(x)
                    self.pos[x] = self.places(x) - {s}

    def flush(self, why, also=()):
        """Store every live (or still used, or in `also`) value that is only in a register."""
        for r in self.regs:
            for v in sorted(self.con[r]):
                if (self.needed(v) or v in also) and v not in self.places(v) - set(self.regs):
                    if self.reg_of(v) == r:
                        self.store(r, v, f"{why}: {v} only in {r} -> ST {r}, {v}")

    def operand_reg(self, x, avoid=()):
        """A register holding x for reading only (x keeps its value)."""
        r = None if is_const(x) else self.reg_of(x)
        if r and r not in avoid:
            self.decisions.append(f"{x} is already in {r}: no load")
            return r
        r = self.getreg(x, avoid)
        self.emit(f"LD {r}, {self.addr(x)}")
        self.clobber(r)
        self.con[r] = set() if is_const(x) else {x}
        if not is_const(x):
            self.pos[x] = self.places(x) | {r}
        return r

    def translate(self, b):
        form, parts = tac.parse_instruction(b)
        if form == "arith":                               # (A) v := x op y
            v, x, op, y = parts
            r = self.getreg(x)
            self.load(r, x)
            self.emit(f"{OPCODE[op]} {r}, {self.addr(y)}")
            self.define(v, r)
            self.drop_dead(x, y)
        elif form == "convert":                           # (B) v := inttofloat x
            v, x = parts
            r = self.getreg(x)
            self.load(r, x)
            self.emit(f"FLT {r}")
            self.define(v, r)
            self.drop_dead(x)
        elif form == "copy" and not is_const(parts[1]):  # (C) v := x
            v, x = parts
            r = self.getreg(x)
            self.load(r, x)
            self.define(v, r, also=(x,) if x != v else ())
            self.drop_dead(x)
        elif form == "copy":                            # (D) v := c
            v, c = parts
            r = self.getreg(v)
            self.emit(f"LD {r}, #{c}")
            self.define(v, r)
        elif form == "array_read":                          # v := a[i]
            v, a, i = parts
            r = self.getreg(i)
            self.load(r, i)
            self.emit(f"LD {r}, {a}[{r}]")
            self.define(v, r)
            self.drop_dead(i)
        elif form == "array_write":                      # a[i] := y
            a, i, y = parts
            if len(self.regs) < 2:
                raise ValueError(f"{b}: storing into an array needs two registers")
            ry = self.operand_reg(y)
            ri = self.operand_reg(i, avoid=(ry,))
            self.emit(f"ST {ry}, {a}[{ri}]")
            self.drop_dead(i, y)
        elif form == "if":                                  # if x cop y goto L
            x, cop, y, label = parts
            r = self.operand_reg(x)
            self.flush("block end")
            self.emit(f"CMP {r}, {self.addr(y)}")
            self.emit(f"{JUMP[cop]} {label}")
        elif form == "goto":
            self.flush("block end")
            self.emit(f"JMP {parts[0]}")
        elif form == "return":
            self.flush("block end")
            self.emit("RET" + (f" {self.addr(parts[0])}" if parts[0] else ""))
        elif form == "param":
            self.emit(f"PARAM {self.addr(parts[0])}")
            self.drop_dead(parts[0])
        elif form == "print":
            self.emit(f"PRINT {self.addr(parts[0])}")
            self.drop_dead(parts[0])
        elif form in ("call", "call_value"):
            f, n = parts[-2:]
            self.flush("before the call", also=self.flush_extra)
            for r in self.regs:
                self.forget_reg(r)
            self.decisions.append("the call may change every register: all registers are free")
            self.emit(f"CALL {f}, {n}")
            if form == "call_value":
                self.decisions.append(f"the result {parts[0]} arrives in R0")
                self.define(parts[0], "R0")
        else:
            raise ValueError(f"cannot translate: {b}")

    def run(self, block_nr=0):
        for self.i, b in enumerate(self.ins):
            self.step_code, self.decisions = [], []
            self.translate(b)
            if self.i == len(self.ins) - 1 and tac.parse_instruction(b)[0] not in ENDS_BLOCK:
                self.flush("block end")
            self.log.append(Step(b, self.step_code, self.decisions, self.snapshot_con(),
                                 self.snapshot_pos(), block_nr))
        return self

    def snapshot_con(self):
        return {r: sorted(self.con[r]) for r in self.regs}

    def snapshot_pos(self):
        return {v: sorted(p, key=lambda q: (q not in self.con, q)) for v, p in sorted(self.pos.items()) if p}


def gen_block(instructions, registers=2, live_end=()):
    """Code for one basic block given as a list of 3AC strings (no jumps needed).
    Returns (assembler lines, log)."""
    g = BlockGen(list(instructions), registers, live_end).run()
    return g.code, g.log


@dataclass
class Result:
    asm: list                  # assembler lines; labels end with ":"
    log: list                  # Step per 3AC instruction
    blocks: list
    program: object            # tac.Program


def generate(tac_text, registers=3, naive=False):
    """Assembler for a whole program (output of `calc -s -t`)."""
    p = tac.read_program(tac_text)
    blocks = liveness(p, split_blocks(p))
    asm, log = [], []
    for b in blocks:
        asm += [m + ":" for m in b.labels]
        ins = p.instructions[b.start:b.end]
        if naive:
            code = naive_block(ins)
            log.append(Step("\n".join(ins), code, ["naive: every operand from memory, every result to memory"],
                            {}, {}, b.nr))
        else:
            g = BlockGen(ins, registers, b.live_out, visible_globals(p, b.function)).run(b.nr)
            code = g.code
            log += g.log
        asm += code
    return Result(asm, log, blocks, p)


def naive_block(instructions):
    """A stereotyped scheme for comparison: one register, load operands, store results."""
    out = []
    a = lambda x: "#" + x if is_const(x) else x  # noqa: E731
    for b in instructions:
        form, parts = tac.parse_instruction(b)
        if form == "arith":
            v, x, op, y = parts
            out += [f"LD R0, {a(x)}", f"{OPCODE[op]} R0, {a(y)}", f"ST R0, {v}"]
        elif form == "copy":
            out += [f"LD R0, {a(parts[1])}", f"ST R0, {parts[0]}"]
        elif form == "convert":
            out += [f"LD R0, {a(parts[1])}", "FLT R0", f"ST R0, {parts[0]}"]
        elif form == "array_read":
            v, arr, i = parts
            out += [f"LD R0, {a(i)}", f"LD R0, {arr}[R0]", f"ST R0, {v}"]
        elif form == "array_write":
            arr, i, y = parts
            out += [f"LD R1, {a(i)}", f"LD R0, {a(y)}", f"ST R0, {arr}[R1]"]
        elif form == "if":
            x, cop, y, label = parts
            out += [f"LD R0, {a(x)}", f"CMP R0, {a(y)}", f"{JUMP[cop]} {label}"]
        elif form == "goto":
            out.append(f"JMP {parts[0]}")
        elif form == "return":
            out.append("RET" + (f" {a(parts[0])}" if parts[0] else ""))
        elif form == "param":
            out.append(f"PARAM {a(parts[0])}")
        elif form == "print":
            out.append(f"PRINT {a(parts[0])}")
        elif form == "call":
            out.append(f"CALL {parts[0]}, {parts[1]}")
        elif form == "call_value":
            out += [f"CALL {parts[1]}, {parts[2]}", f"ST R0, {parts[0]}"]
    return out


# --- simulator ------------------------------------------------------------------------------

class MachineError(Exception):
    pass


class Machine:
    """Runs the assembler. Memory: one frame per call (names from the symbol tables of the
    3AC program); a name not in the current function's table is a global of main."""

    def __init__(self, asm, program, registers=3, max_steps=500_000):
        self.p = program
        self.lines = [l for l in asm if not l.endswith(":")]
        self.labels, n = {}, 0
        for l in asm:
            if l.endswith(":"):
                self.labels[l[:-1]] = n
            else:
                n += 1
        self.regs = {f"R{i}": None for i in range(max(registers, 1))}
        self.glob = {}
        self.frames = [("main", self.glob, None)]          # (function, memory, return pc)
        self.params, self.output, self.flag = [], [], None
        self.pc, self.steps, self.max_steps = 0, 0, max_steps

    def cell(self, name):
        f, mem, _ = self.frames[-1]
        if f != "main" and name in self.p.frames[f].entries:
            return mem
        return self.glob

    def value(self, x):
        if x.startswith("#"):
            return tac.number(x[1:])
        if x in self.regs:
            v = self.regs[x]
        elif m := re.fullmatch(r"(\w+)\[(R\d+)\]", x):
            v = self.cell(m[1]).get((m[1], self.regs[m[2]]), 0)
        else:
            v = self.cell(x).get(x)
        if v is None:
            raise MachineError(f"read without a value: {x}")
        return v

    def put(self, x, v):
        if x in self.regs:
            self.regs[x] = v
        elif m := re.fullmatch(r"(\w+)\[(R\d+)\]", x):
            self.cell(m[1])[(m[1], self.regs[m[2]])] = v
        else:
            self.cell(x)[x] = v

    def step(self):
        line = self.lines[self.pc]
        op, _, rest = line.partition(" ")
        args = [a.strip() for a in rest.split(",")] if rest else []
        self.pc += 1
        if op == "LD":
            self.regs[args[0]] = self.value(args[1])
        elif op == "ST":
            self.put(args[1], self.value(args[0]))
        elif op == "MOV":
            self.put(args[1], self.value(args[0]))
        elif op in ("ADD", "SUB", "MUL", "DIV"):
            sym = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/"}[op]
            self.regs[args[0]] = tac.compute(self.value(args[0]), sym, self.value(args[1]))
        elif op == "INC":
            self.put(args[0], self.value(args[0]) + 1)
        elif op == "DEC":
            self.put(args[0], self.value(args[0]) - 1)
        elif op == "SHL":
            self.regs[args[0]] = self.value(args[0]) << self.value(args[1])
        elif op == "FLT":
            self.regs[args[0]] = float(self.value(args[0]))
        elif op == "CMP":
            self.flag = (self.value(args[0]), self.value(args[1]))
        elif op in JUMP.values():
            cop = {j: c for c, j in JUMP.items()}[op]
            if tac.COMPARE[cop](*self.flag):
                self.pc = self.labels[args[0]]
        elif op == "JMP":
            self.pc = self.labels[args[0]]
        elif op == "PARAM":
            self.params.append(self.value(args[0]))
        elif op == "CALL":
            f, n = args[0], int(args[1])
            given, self.params = self.params[-n:] if n else [], self.params[:len(self.params) - n]
            params = sorted((e for e in self.p.frames[f].entries.values() if e.kind == "param"),
                            key=lambda e: e.offset)
            if len(params) != n:
                raise MachineError(f"{f} expects {len(params)} arguments")
            self.frames.append((f, {e.name: v for e, v in zip(params, given)}, self.pc))
            self.pc = self.labels[f]
        elif op == "RET":
            if args:
                self.regs["R0"] = self.value(args[0])
            _, _, back = self.frames.pop()
            self.pc = back
        elif op == "PRINT":
            self.output.append(tac.g(self.value(args[0])))
        else:
            raise MachineError(f"unknown instruction: {line}")

    def run(self):
        while self.pc < len(self.lines):
            self.steps += 1
            if self.steps > self.max_steps:
                raise MachineError("too many steps")
            self.step()
        return self

    def globals(self):
        """Final values of main's variables (arrays as lists), like tac.Machine.global_values()."""
        out = {}
        for e in self.p.frames["main"].entries.values():
            if e.kind != "var":
                continue
            if e.length:
                out[e.name] = [self.glob.get((e.name, 4 * i), 0) for i in range(e.length)]
            elif e.name in self.glob:
                out[e.name] = self.glob[e.name]
        return out


def run(asm, program, registers=3):
    return Machine(asm, program, registers).run()


# --- display --------------------------------------------------------------------------------

def listing(asm):
    return "\n".join(l if l.endswith(":") else "    " + l for l in asm)


def show_step(s):
    out = [s.tac]
    out += ["    " + c for c in s.code] or ["    (no instruction)"]
    out += ["    ; " + d for d in s.decisions]
    out.append("    Con: " + "  ".join(f"{r}={{{', '.join(v)}}}" for r, v in s.con.items()))
    out.append("    Pos: " + "  ".join(f"{v}={{{', '.join(p)}}}" for v, p in s.pos.items()))
    return "\n".join(out)


def show_log(log):
    out, block = [], None
    for s in log:
        if s.block != block:
            block = s.block
            out.append(f"--- block B{block + 1}")
        out.append(show_step(s))
    return "\n".join(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    text = open(args[0]).read()
    registers = int(args[1]) if len(args) > 1 else 3
    r = generate(text, registers, naive="--naive" in sys.argv)
    if "--log" in sys.argv:
        print(show_log(r.log))
        print()
    print(listing(r.asm))
    m = run(r.asm, r.program, registers)
    print(f"; {len([l for l in r.asm if not l.endswith(':')])} instructions, {m.steps} steps")
    for line in m.output:
        print("; output", line)
    for k, v in m.globals().items():
        print(f"; {k} = {v}")


if __name__ == "__main__":
    main()
