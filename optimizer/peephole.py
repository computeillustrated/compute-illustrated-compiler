"""Peephole optimization: a small window (up to three lines) slides over the assembler from
codegen.py; wherever a rule matches, the lines in the window are replaced.

Rules
  redundant load       ST R, a / LD R, a              -> ST R, a
  redundant store      LD R, a / ST R, a              -> LD R, a
  jump over jump       Jcc L1 / JMP L2 / L1:          -> J!cc L2 / L1:
  jump to next line    JMP L / L:                     -> L:
  jump to jump         JMP L1 (L1: JMP L2)            -> JMP L2   (also Jcc)
  unreachable code     JMP L / X (no label before X)  -> JMP L    (also after RET)
  unused label         L: (no jump to L)              -> (gone)
  algebraic identity   ADD R, #0  SUB R, #0  MUL R, #1  DIV R, #1  LD R, R  -> (gone)
  special instruction  ADD R, #1 -> INC R    SUB R, #1 -> DEC R    MUL R, #2^k -> SHL R, #k
  store constant       LD R, #c / ST R, v (R not read afterwards) -> MOV #c, v

"R not read afterwards" looks ahead to the end of the block: the code generator never
expects a value in a register after a label, a jump or a call.

Usage:  python peephole.py prog.tac [registers] [--naive]
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codegen  # noqa: E402

NEGATE = {"JLT": "JGE", "JGE": "JLT", "JLE": "JGT", "JGT": "JLE", "JEQ": "JNE", "JNE": "JEQ"}
JUMPS = set(NEGATE) | {"JMP"}


def parse(line):
    """(opcode, [args]) or ("label", [name])."""
    if line.endswith(":"):
        return "label", [line[:-1]]
    op, _, rest = line.partition(" ")
    return op, [a.strip() for a in rest.split(",")] if rest else []


def is_label(line):
    return line.endswith(":")


def reads_reg(line, r):
    op, args = parse(line)
    if op == "LD":
        return r in re.findall(r"R\d+", args[1])
    return r in re.findall(r"R\d+", " ".join(args))


def reg_dead_after(lines, j, r):
    """r is not read again before the end of the block, starting at lines[j]."""
    for line in lines[j:]:
        op, args = parse(line)
        if op == "label" or op in JUMPS or op == "CALL":
            return True
        if reads_reg(line, r):
            return False
        if op == "LD" and args[0] == r:
            return True
        if op == "RET":
            return True
    return True


def first_instruction(lines, label):
    i = lines.index(label + ":")
    for line in lines[i + 1:]:
        if not is_label(line):
            return line
    return None


def referenced(lines):
    names = set()
    for line in lines:
        op, args = parse(line)
        if op in JUMPS:
            names.add(args[0])
        elif op == "CALL":
            names.add(args[0])
    return names


def try_rules(lines, i):
    """Tries every rule on the window starting at i. Returns (rule, width, new lines) or None."""
    w = lines[i:i + 3]
    a = parse(w[0])
    b = parse(w[1]) if len(w) > 1 else (None, [])
    c = parse(w[2]) if len(w) > 2 else (None, [])
    if a[0] == "ST" and b[0] == "LD" and a[1] == b[1]:
        return "redundant load", 2, [w[0]]
    if a[0] == "LD" and b[0] == "ST" and a[1] == b[1]:
        return "redundant store", 2, [w[0]]
    if a[0] in NEGATE and b[0] == "JMP" and c == ("label", a[1]):
        return "jump over jump", 3, [f"{NEGATE[a[0]]} {b[1][0]}", w[2]]
    if a[0] == "JMP" and is_label(w[1] if len(w) > 1 else ""):
        # the target may be any of the labels directly below
        j = i + 1
        while j < len(lines) and is_label(lines[j]):
            if lines[j] == a[1][0] + ":":
                return "jump to next line", 1, []
            j += 1
    if a[0] in JUMPS:
        target = first_instruction(lines, a[1][0])
        if target and parse(target)[0] == "JMP" and parse(target)[1][0] != a[1][0]:
            return "jump to jump", 1, [f"{a[0]} {parse(target)[1][0]}"]
    if a[0] in ("JMP", "RET") and len(w) > 1 and not is_label(w[1]):
        return "unreachable code", 2, [w[0]]
    if a[0] == "label" and a[1][0] not in referenced(lines) and not a[1][0].startswith("main"):
        return "unused label", 1, []
    if a[0] in ("ADD", "SUB") and a[1][1] == "#0" or a[0] in ("MUL", "DIV") and a[1][1:] == ["#1"]:
        return "algebraic identity", 1, []
    if a[0] == "LD" and a[1][0] == a[1][1]:
        return "algebraic identity", 1, []
    if a[0] in ("ADD", "SUB") and a[1][1] == "#1":
        return "special instruction", 1, [f"{'INC' if a[0] == 'ADD' else 'DEC'} {a[1][0]}"]
    if a[0] == "MUL" and re.fullmatch(r"#\d+", a[1][1]):
        k = int(a[1][1][1:])
        if k > 1 and k & (k - 1) == 0:
            return "special instruction", 1, [f"SHL {a[1][0]}, #{k.bit_length() - 1}"]
    if (a[0] == "LD" and a[1][1].startswith("#") and b[0] == "ST" and b[1][0] == a[1][0]
            and "[" not in b[1][1] and reg_dead_after(lines, i + 2, a[1][0])):
        return "store constant", 2, [f"MOV {a[1][1]}, {b[1][1]}"]
    return None


@dataclass
class Change:
    position: int              # index of the first window line (labels count)
    rule: str
    before: list               # lines removed
    after: list                # lines inserted
    window: list               # the whole window at that moment


def optimize(asm):
    """Returns (new assembler, list of Change)."""
    lines, log, i = list(asm), [], 0
    while i < len(lines):
        hit = try_rules(lines, i)
        if hit is None:
            i += 1
            continue
        rule, width, new = hit
        log.append(Change(i, rule, lines[i:i + width], new, lines[i:i + 3]))
        lines[i:i + width] = new
        i = max(0, i - 2)                    # the window slides back: a change can enable another
    return lines, log


def check(asm_before, asm_after, program, registers=3):
    """Both versions compute the same output and final values (simulator)."""
    m1 = codegen.run(asm_before, program, registers)
    m2 = codegen.run(asm_after, program, registers)
    assert m1.output == m2.output and m1.globals() == m2.globals(), "peephole changed the meaning"
    return m1, m2


def show_log(log):
    out = []
    for c in log:
        out.append(f"@{c.position:<3} {c.rule}: " + " / ".join(c.before) + "  ->  "
                   + (" / ".join(c.after) if c.after else "(gone)"))
    return "\n".join(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    registers = int(args[1]) if len(args) > 1 else 3
    r = codegen.generate(open(args[0]).read(), registers, naive="--naive" in sys.argv)
    new, log = optimize(r.asm)
    print(show_log(log))
    print()
    print(codegen.listing(new))
    m1, m2 = check(r.asm, new, r.program, registers)
    count = lambda a: len([l for l in a if not is_label(l)])  # noqa: E731
    print(f"; {count(r.asm)} -> {count(new)} instructions, {m1.steps} -> {m2.steps} steps")


if __name__ == "__main__":
    main()
