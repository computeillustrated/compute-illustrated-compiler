"""An abstract stack machine for postfix code.

Instructions (from representations.stack_code, one per postfix word):
    const 10   pushes the number 10
    var x      pushes the value of x
    lvar x     pushes the address of x (the target of an assignment), shown as &x
    add sub mul div   pop the top two entries and push the result
    store      pops a value and the address below it, writes the value to the address

Every step comes back as a dict: program counter before the instruction, instruction, stack
and memory after it. Arithmetic as in the calculator: int / int truncates, otherwise float.

Usage:  python stack_machine.py "x = 10 + 2 * 3"
        python stack_machine.py "y = x * 2 + x * 2 * 3" x=16
"""
import sys
from dataclasses import dataclass

from representations import ast, parse_tree, postfix, stack_code


@dataclass(frozen=True)
class Address:
    name: str

    def __str__(self):
        return f"&{self.name}"


def compute(op, a, b):
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    if isinstance(a, int) and isinstance(b, int):
        q = abs(a) // abs(b)
        return q if (a >= 0) == (b >= 0) else -q
    return a / b


def number(text):
    return float(text) if "." in text else int(text)


def run(instructions, memory=None):
    """Runs the instructions. Returns the list of steps; step 0 is the initial state
    (instruction None)."""
    memory = dict(memory or {})
    stack = []
    steps = [{"pc": 0, "instruction": None, "stack": [], "memory": dict(memory)}]
    for pc, (op, arg) in enumerate(instructions):
        if op == "const":
            stack.append(number(arg))
        elif op == "var":
            if arg not in memory:
                raise KeyError(f"{arg} has no value yet")
            stack.append(memory[arg])
        elif op == "lvar":
            stack.append(Address(arg))
        elif op == "store":
            value = stack.pop()
            target = stack.pop()
            assert isinstance(target, Address), "store needs an address below the value"
            memory[target.name] = value
        else:
            b = stack.pop()
            a = stack.pop()
            stack.append(compute(op, a, b))
        steps.append({"pc": pc, "instruction": f"{op} {arg}" if arg else op,
                      "stack": list(stack), "memory": dict(memory)})
    return steps


def for_line(line, memory=None, expression_only=False):
    """Generates and runs the stack code of an assignment. expression_only=True takes only
    the right-hand side (e.g. `10 2 3 * +` without lvar/store)."""
    a = ast(parse_tree(line))
    if expression_only:
        a = a.children[1]
    code = stack_code(a)
    return {"postfix": postfix(a), "code": code, "steps": run(code, memory)}


def show(stack):
    return "[" + " ".join(str(x) for x in stack) + "]"


def main():
    memory = {}
    for pair in sys.argv[2:]:
        name, value = pair.split("=")
        memory[name] = number(value)
    r = for_line(sys.argv[1], memory)
    print("Postfix:", " ".join(r["postfix"]))
    for s in r["steps"][1:]:
        print(f"{s['pc']:2}  {s['instruction']:<10} {show(s['stack']):<16} {s['memory']}")


if __name__ == "__main__":
    main()
