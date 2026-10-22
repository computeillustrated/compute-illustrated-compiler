"""Procedure frames with control link, access link and display.

The example `shop.py` (nested functions) really runs, under `sys.settrace`. The real run
gives the calls and returns (with arguments, return value and return line) and every read
of a variable of an enclosing function (instruction LOAD_DEREF, via sys.monitoring). Next to
it, the model keeps a stack of frames as a compiled program would:

- Control link: points to the caller's frame.
- Access link: points to the frame of the function that directly encloses the callee in the
  program text. The caller finds it by following (depth of caller − depth of callee + 1)
  access links, starting from itself.
- Display D[i]: points to the newest frame of nesting depth i. When a function of depth i
  is called, the old value of D[i] is saved in the new frame and restored on return.

Reading a variable of depth j from a function of depth k follows k − j access links
(relative depth) or takes D[j] directly. Both are checked against the real run: the frame
found this way holds exactly the value Python read.

Usage:  python frames.py
"""
import dis
import io
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent / "shop.py"


@dataclass
class Frame:
    num: int                # 0 = bottom frame (main)
    name: str
    depth: int              # static nesting depth
    control: int | None     # number of the caller's frame
    access: int | None      # number of the frame of the enclosing function
    saved: int | None       # old value of D[depth] (None = was empty)
    return_line: int | None  # line in the caller where execution continues
    params: dict = field(default_factory=dict)
    locals: dict = field(default_factory=dict)     # current values (without functions)

    def short(self):
        args = ", ".join(f"{k} = {v}" for k, v in self.params.items())
        return f"{self.name}({args})"


@dataclass
class Step:
    kind: str               # "call", "return", "read"
    frame: int              # frame concerned (called, returning, reading)
    stack: list             # copy of the frames (bottom first)
    display: list           # D[0..], frame numbers or None
    name: str | None = None         # read: variable
    value: object = None            # read: value read; return: return value
    defined_at: int | None = None   # read: depth of the definition
    relative: int | None = None     # read: relative depth (number of access links)
    chain: list | None = None       # read: frames visited along the access links
    line: int | None = None         # read: line in shop.py


def depth_of(code):
    return code.co_qualname.count("<locals>")


def parent_name(code):
    parts = code.co_qualname.split(".<locals>.")
    return ".<locals>.".join(parts[:-1]) or None


def function_names(code):
    """Names of all functions defined in `code` and below."""
    names = set()
    for c in code.co_consts:
        if hasattr(c, "co_code"):
            names.add(c.co_name)
            names |= function_names(c)
    return names


def all_codes(code):
    """The code objects of all functions in `code` (without the module itself)."""
    for c in code.co_consts:
        if hasattr(c, "co_code"):
            yield c
            yield from all_codes(c)


def run(path=EXAMPLE):
    """Runs the example; returns (steps, output of the program)."""
    source = Path(path).read_text()
    module = compile(source, str(path), "exec")
    not_variables = function_names(module)
    filename = str(path)

    stack = []                  # Frame objects of the model
    py = []                     # the matching Python frames
    display = []
    steps = []
    instructions = {}           # code -> {offset: Instruction}

    def copy():
        return [Frame(**{**r.__dict__, "params": dict(r.params), "locals": dict(r.locals)})
                for r in stack]

    def local_values(frame):
        return {k: v for k, v in frame.f_locals.items()
                if k not in not_variables and not callable(v)}

    def update():
        for r, f in zip(stack, py):
            r.locals = local_values(f)

    def on_instruction(code, offset):
        """sys.monitoring: before every instruction of a function from the example."""
        if code not in instructions:
            instructions[code] = {i.offset: i for i in dis.get_instructions(code)}
        instruction = instructions[code].get(offset)
        if not (instruction and instruction.opname == "LOAD_DEREF"
                and instruction.argval not in not_variables):
            return
        frame = sys._getframe(1)
        name = instruction.argval
        r = stack[-1]
        assert py[-1] is frame
        # Where is name defined? In the nearest enclosing function that has it.
        target = r.num
        chain = [target]
        while name not in (py[target].f_code.co_cellvars + py[target].f_code.co_varnames):
            target = stack[target].access
            chain.append(target)
        j = stack[target].depth
        assert len(chain) - 1 == r.depth - j            # relative depth = k − j
        assert display[j] == target                     # the display finds the same frame
        value = py[target].f_locals[name]
        assert value == frame.f_locals[name]            # the same value as in Python
        update()
        steps.append(Step("read", r.num, copy(), list(display), name, value,
                          j, r.depth - j, chain, frame.f_lineno))

    def tracer(frame, event, arg):
        code = frame.f_code
        if code.co_filename != filename or code.co_name == "<module>":
            return tracer
        if event == "call":
            t = depth_of(code)
            caller = stack[-1] if stack else None
            if caller is None:
                access = None
            else:
                # Rule: from the caller, follow (depth of caller − new depth + 1) access links
                target = caller.num
                for _ in range(caller.depth - t + 1):
                    target = stack[target].access
                access = target
                # Cross-check: the newest frame of the enclosing function
                parent = parent_name(code)
                newest = max(i for i, f in enumerate(py) if f.f_code.co_qualname == parent)
                assert access == newest, (code.co_qualname, access, newest)
            while len(display) <= t:
                display.append(None)
            params = {n: frame.f_locals[n] for n in code.co_varnames[:code.co_argcount]}
            r = Frame(len(stack), code.co_name, t,
                      caller.num if caller else None, access, display[t],
                      py[-1].f_lineno if py else None, params)
            stack.append(r)
            py.append(frame)
            display[t] = r.num
            update()
            steps.append(Step("call", r.num, copy(), list(display)))
        elif event == "return":
            r = stack[-1]
            update()
            steps.append(Step("return", r.num, copy(), list(display), value=arg))
            display[r.depth] = r.saved
            stack.pop()
            py.pop()
        return tracer

    output = io.StringIO()
    mon = sys.monitoring
    tool = mon.DEBUGGER_ID
    mon.use_tool_id(tool, "frames")
    mon.register_callback(tool, mon.events.INSTRUCTION, on_instruction)
    for code in all_codes(module):
        mon.set_local_events(tool, code, mon.events.INSTRUCTION)
    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        with redirect_stdout(output):
            exec(module, {"__name__": "__main__"})
    finally:
        sys.settrace(old)
        for code in all_codes(module):
            mon.set_local_events(tool, code, 0)
        mon.register_callback(tool, mon.events.INSTRUCTION, None)
        mon.free_tool_id(tool)
    return steps, output.getvalue()


def show(steps):
    for s in steps:
        r = s.stack[s.frame]
        d = " ".join(f"D[{i}]={'-' if x is None else x}" for i, x in enumerate(s.display))
        if s.kind == "call":
            print(f"call   #{r.num} {r.short():14} depth {r.depth}  control -> {r.control}  "
                  f"access -> {r.access}  saved D[{r.depth}] = {r.saved}  "
                  f"return to line {r.return_line}   {d}")
        elif s.kind == "read":
            print(f"read   #{r.num} {r.name} reads {s.name} = {s.value} (line {s.line}): defined at depth "
                  f"{s.defined_at}, relative depth {s.relative}, chain {' -> '.join(map(str, s.chain))}, "
                  f"display D[{s.defined_at}]")
        else:
            print(f"return #{r.num} {r.short():14} value {s.value}   {d}")


if __name__ == "__main__":
    steps, output = run()
    show(steps)
    print("output:", output.strip())
    deepest = max((s for s in steps), key=lambda s: len(s.stack))
    print("highest stack:", " | ".join(f"#{r.num} {r.short()} c={r.control} a={r.access}"
                                       for r in deepest.stack))
