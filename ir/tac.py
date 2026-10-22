"""Runs three-address code as the calculator prints it with `-s -t`.

A small abstract machine: a memory STORE with byte addresses (one cell per 4-byte word),
a program counter pc and procedure frames on a stack. The symbol tables (`# frame …`
comments) belong to the program: they give the offset and type of every variable,
addr(v) = display[depth] + offset(v).

Frame of a function (as in the calculator, offsets in bytes):
    0 result   4 saved pc   8 saved depth   12 saved display[1]
    16 … parameters, local variables, temporaries
The top level (main) has depth 0 and starts at address 0, without bookkeeping fields.
Functions have depth 1 (no nested functions); display[1] points to the frame of the running
call, and call saves its old value in the new frame.

Stricter than necessary, so that mistakes in the generator show up: + - * / and comparisons
need equal types (a missing inttofloat stops the machine), an assignment must match the type
in the symbol table, and reading a cell without a value is an error.

Usage:  python tac.py prog.tac            output and final values of the global variables
        python tac.py prog.tac --steps    also every step
"""
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HEADER_SIZE = 16               # bookkeeping fields at the start of a function frame
HEADER_FIELDS = {0: "result", 4: "saved pc", 8: "saved depth", 12: "saved display"}


class TacError(Exception):
    pass


@dataclass
class Entry:
    name: str
    type: str       # "int", "float"
    kind: str       # "var", "param", "temp"
    size: int
    offset: int
    length: int = 0  # arrays: number of elements


@dataclass
class Frame:
    """Symbol table of one frame (main or a function)."""
    name: str
    depth: int
    size: int
    entries: dict = field(default_factory=dict)


@dataclass
class Program:
    instructions: list      # instruction texts without labels
    labels: dict            # label → index of the next instruction
    frames: dict            # name → Frame
    labels_before: dict     # index → labels right before it (for display)


def number(text):
    """A constant in 3AC: float with a dot or exponent, otherwise int; None if not a number."""
    if re.fullmatch(r"\d+", text):
        return int(text)
    if re.fullmatch(r"\d+\.\d*(e[+-]?\d+)?|\d+e[+-]?\d+", text):
        return float(text)
    return None


def read_program(text):
    """Splits the output of `calc -s -t` into instructions, labels and symbol tables."""
    instructions, labels, frames, before = [], {}, {}, {}
    current = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            if m := re.match(r"# frame (\w+), depth (\d+), size (\d+)", line):
                current = frames[m[1]] = Frame(m[1], int(m[2]), int(m[3]))
            elif (parts := line[1:].split()) and parts[0] != "name":
                name, typ, kind, size, offset = parts
                length = 0
                if m := re.fullmatch(r"(\w+)\[(\d+)\]", typ):
                    typ, length = m[1], int(m[2])
                current.entries[name] = Entry(name, typ, kind, int(size), int(offset), length)
            continue
        if line.rstrip().endswith(":") and not line.startswith(" "):
            label = line.strip()[:-1]
            labels[label] = len(instructions)
            before.setdefault(len(instructions), []).append(label)
        else:
            instructions.append(line.strip())
    if "main" not in frames:
        raise TacError("no symbol table in the program (use calc -s -t)")
    return Program(instructions, labels, frames, before)


# Instruction forms, tried in this order
NAME = r"[A-Za-z_]\w*"
ARG = r"[\w.+-]+"
FORMS = [
    ("goto", re.compile(rf"goto ({NAME})$")),
    ("if", re.compile(rf"if ({ARG}) (<=|>=|==|!=|<|>) ({ARG}) goto ({NAME})$")),
    ("call_value", re.compile(rf"({NAME}) := call ({NAME}), (\d+)$")),
    ("call", re.compile(rf"call ({NAME}), (\d+)$")),
    ("param", re.compile(rf"param ({ARG})$")),
    ("return", re.compile(rf"return(?: ({ARG}))?$")),
    ("print", re.compile(rf"print ({ARG})$")),
    ("convert", re.compile(rf"({NAME}) := inttofloat ({ARG})$")),
    ("array_read", re.compile(rf"({NAME}) := ({NAME})\[({ARG})\]$")),
    ("array_write", re.compile(rf"({NAME})\[({ARG})\] := ({ARG})$")),
    ("arith", re.compile(rf"({NAME}) := ({ARG}) ([-+*/]) ({ARG})$")),
    ("copy", re.compile(rf"({NAME}) := ({ARG})$")),
]


def parse_instruction(instruction):
    """(form, parts) of an instruction, e.g. ("arith", ("t1", "2", "*", "3"))."""
    for form, pattern in FORMS:
        if m := pattern.match(instruction):
            return form, m.groups()
    raise TacError(f"unknown instruction: {instruction}")


def type_of(value):
    return "float" if isinstance(value, float) else "int"


def compute(a, op, b):
    if type_of(a) != type_of(b):
        raise TacError(f"mixed types {a} {op} {b} (missing inttofloat?)")
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if b == 0:
        raise TacError("division by zero")
    if isinstance(a, int):
        q = abs(a) // abs(b)               # like C: truncate towards zero
        return q if (a >= 0) == (b >= 0) else -q
    return a / b


COMPARE = {"<": lambda a, b: a < b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b,
           ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


def g(value):
    """A number as printf("%g") prints it in the calculator."""
    return "%g" % value


class Machine:
    def __init__(self, program, max_steps=200_000):
        self.p = program
        self.store = {}                     # address → value
        self.display = [0, None]            # display[0] = main, display[1] = running function
        self.depth = 0
        self.newframe = program.frames["main"].size
        self.param = self.newframe + HEADER_SIZE
        self.pc = 0
        self.calls = [("main", 0)]          # (function, base address), for names and display only
        self.output = []
        self.max_steps = max_steps
        self.zero_arrays("main", 0)

    # --- Addresses ------------------------------------------------------------
    def entry(self, name):
        """(Entry, base address) of a name: first the running function, then main."""
        function, base = self.calls[-1]
        if function != "main" and name in self.p.frames[function].entries:
            return self.p.frames[function].entries[name], base
        if name in self.p.frames["main"].entries:
            return self.p.frames["main"].entries[name], self.display[0]
        raise TacError(f"{name} is in no symbol table")

    def addr(self, name):
        e, base = self.entry(name)
        return base + e.offset

    def value(self, arg):
        if (z := number(arg)) is not None:
            return z
        a = self.addr(arg)
        if a not in self.store:
            raise TacError(f"{arg} has no value yet")
        return self.store[a]

    def write(self, name, value, offset=None):
        e, base = self.entry(name)
        if type_of(value) != e.type:
            raise TacError(f"{e.type} {name} gets {type_of(value)} {value}")
        a = base + e.offset
        if offset is not None:
            if not e.length:
                raise TacError(f"{name} is not an array")
            if offset % 4 or not 0 <= offset < 4 * e.length:
                raise TacError(f"index out of range for {name}: offset {offset}")
            a += offset
        self.store[a] = value
        return a

    def read_array(self, name, offset):
        e, base = self.entry(name)
        if not e.length:
            raise TacError(f"{name} is not an array")
        if offset % 4 or not 0 <= offset < 4 * e.length:
            raise TacError(f"index out of range for {name}: offset {offset}")
        return self.store[base + e.offset + offset]

    def zero_arrays(self, function, base):
        """Arrays start out all zeros, as in the calculator."""
        for e in self.p.frames[function].entries.values():
            for i in range(e.length):
                self.store[base + e.offset + 4 * i] = 0.0 if e.type == "float" else 0

    # --- Running --------------------------------------------------------------
    def step(self):
        """Runs the instruction at pc. Returns what it wrote: [(address, value)]."""
        instruction = self.p.instructions[self.pc]
        form, t = parse_instruction(instruction)
        nxt = self.pc + 1
        written = []
        if form == "goto":
            nxt = self.p.labels[t[0]]
        elif form == "if":
            a, b = self.value(t[0]), self.value(t[2])
            if type_of(a) != type_of(b):
                raise TacError(f"mixed types in {instruction} (missing inttofloat?)")
            if COMPARE[t[1]](a, b):
                nxt = self.p.labels[t[3]]
        elif form == "arith":
            v = compute(self.value(t[1]), t[2], self.value(t[3]))
            written.append((self.write(t[0], v), v))
        elif form == "copy":
            v = self.value(t[1])
            written.append((self.write(t[0], v), v))
        elif form == "convert":
            v = self.value(t[1])
            if not isinstance(v, int):
                raise TacError(f"inttofloat gets {v}")
            written.append((self.write(t[0], float(v)), float(v)))
        elif form == "array_read":
            v = self.read_array(t[1], self.value(t[2]))
            written.append((self.write(t[0], v), v))
        elif form == "array_write":
            v = self.value(t[2])
            written.append((self.write(t[0], v, self.value(t[1])), v))
        elif form == "param":
            v = self.value(t[0])
            self.store[self.param] = v
            written.append((self.param, v))
            self.param += 4
        elif form in ("call", "call_value"):
            f, n = (t[1], int(t[2])) if form == "call_value" else (t[0], int(t[1]))
            nxt = self.call(f, n, written)
        elif form == "return":
            nxt = self.ret(t[0], written)
        elif form == "print":
            self.output.append(g(self.value(t[0])))
        self.pc = nxt
        return written

    def call(self, f, n, written):
        frame = self.p.frames[f]
        params = [e for e in frame.entries.values() if e.kind == "param"]
        if len(params) != n or self.param != self.newframe + HEADER_SIZE + 4 * n:
            raise TacError(f"call {f}, {n}: expects {len(params)} parameters, "
                           f"got {(self.param - self.newframe - HEADER_SIZE) // 4}")
        base = self.newframe
        for e in params:
            if type_of(self.store[base + e.offset]) != e.type:
                raise TacError(f"parameter {e.name} of {f} is {e.type}")
        # Clear the rest of the new frame: no value from an earlier call stays readable
        for a in range(base, base + frame.size, 4):
            if not HEADER_SIZE <= a - base < HEADER_SIZE + 4 * n:
                self.store.pop(a, None)
        for offset, v in ((4, self.pc + 1), (8, self.depth), (12, self.display[1])):
            self.store[base + offset] = v
            written.append((base + offset, v))
        self.depth = frame.depth
        self.display[1] = base
        self.newframe = base + frame.size
        self.param = self.newframe + HEADER_SIZE
        self.calls.append((f, base))
        self.zero_arrays(f, base)
        return self.p.labels[f]

    def ret(self, arg, written):
        if self.depth == 0:
            raise TacError("return outside a function")
        base = self.display[self.depth]
        if arg is not None:
            v = self.value(arg)
            self.store[base] = v
            written.append((base, v))
        self.newframe = base
        self.param = self.newframe + HEADER_SIZE
        self.display[self.depth] = self.store[base + 12]
        self.depth = self.store[base + 8]
        nxt = self.store[base + 4]
        self.calls.pop()
        # Fetch the result (getresult) if the call was "x := call f, n"
        form, t = parse_instruction(self.p.instructions[nxt - 1])
        if form == "call_value":
            if base not in self.store or arg is None:
                raise TacError(f"{t[1]} returns no result")
            v = self.store[base]
            written.append((self.write(t[0], v), v))
        return nxt

    def run(self, steps=None):
        """Runs the program to the end. With a list `steps`, every step is appended as a dict
        (see state())."""
        n = 0
        while self.pc < len(self.p.instructions):
            n += 1
            if n > self.max_steps:
                raise TacError("too many steps (endless loop?)")
            pc, instruction = self.pc, self.p.instructions[self.pc]
            written = self.step()
            if steps is not None:
                steps.append({"pc": pc, "instruction": instruction, "written": written,
                              **self.state()})
        return self

    # --- Display --------------------------------------------------------------
    def state(self):
        """Registers and all frames with names, for animations and tests."""
        frames = []
        for function, base in self.calls:
            table = self.p.frames[function]
            cells = []
            if function != "main":
                cells += [(o, n, self.store.get(base + o)) for o, n in HEADER_FIELDS.items()]
            for e in table.entries.values():
                for i in range(max(1, e.length)):
                    name = f"{e.name}[{i}]" if e.length else e.name
                    cells.append((e.offset + 4 * i, name, self.store.get(base + e.offset + 4 * i)))
            frames.append({"function": function, "base": base, "size": table.size, "cells": cells})
        return {"next_pc": self.pc, "depth": self.depth, "display": list(self.display),
                "newframe": self.newframe, "param": self.param, "output": list(self.output),
                "frames": frames}

    def global_values(self):
        """Final values of the variables of main (without temporaries); arrays as lists."""
        values = {}
        for e in self.p.frames["main"].entries.values():
            if e.kind != "var":
                continue
            if e.length:
                values[e.name] = [self.store.get(e.offset + 4 * i) for i in range(e.length)]
            elif e.offset in self.store:
                values[e.name] = self.store[e.offset]
        return values


def run(text, steps=None):
    """Reads and starts a 3AC program. Returns the machine after the run."""
    return Machine(read_program(text)).run(steps)


# --- Building and running the real calculator --------------------------------------------

# The calculator's sources: calculator/ next to this file if it exists, else the folder above
# (in the public repository, tac.py lives in ir/ and the calculator in the root folder).
_HERE = Path(__file__).resolve().parent
CALCULATOR_DIR = next(d for d in (_HERE / "calculator", _HERE.parent) if (d / "calc.y").is_file())
_built = {}


def build_calculator(debug=False):
    """Builds the calculator from CALCULATOR_DIR in its own temporary folder (yacc, lex, cc as
    run.sh does) and returns the path to the program. Once per process and variant."""
    if debug not in _built:
        folder = Path(tempfile.mkdtemp(prefix="tac_calculator_"))
        for name in ("calc.y", "calc.l", "value.h", "tac.c"):
            shutil.copy(CALCULATOR_DIR / name, folder / name)
        subprocess.run(["yacc", "-d", "calc.y"], cwd=folder, check=True, capture_output=True)
        subprocess.run(["lex", "calc.l"], cwd=folder, check=True, capture_output=True)
        subprocess.run(["cc", *(["-DYYDEBUG=1"] if debug else []), "-o", "calc", "y.tab.c", "lex.yy.c"],
                       cwd=folder, check=True, capture_output=True)
        _built[debug] = folder / "calc"
    return _built[debug]


def run_calculator(source, *options, debug=False):
    """Runs the calculator with the options ("-t", "-s", "-c") on the source text.
    Returns (output as text, exit code); stderr appears at its place in the output."""
    result = subprocess.run([str(build_calculator(debug)), *options], input=source.rstrip("\n") + "\n",
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return result.stdout, result.returncode


def main():
    path = sys.argv[1]
    steps = [] if "--steps" in sys.argv else None
    m = run(open(path).read(), steps)
    for s in steps or []:
        print(f"{s['pc']:3}  {s['instruction']:<26} depth {s['depth']}  newframe {s['newframe']:3}  "
              + "  ".join(f"[{a}] := {v}" for a, v in s["written"]))
    for line in m.output:
        print(line)
    for name, w in m.global_values().items():
        print(f"{name} = " + ("[" + ", ".join(g(x) for x in w) + "]" if isinstance(w, list) else g(w)))


if __name__ == "__main__":
    main()
