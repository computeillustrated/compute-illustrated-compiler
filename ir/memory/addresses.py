"""Episode 29: real addresses, relative to each other.

1. `regions.c`: code, a global, a static local, a local and a malloc'ed
   variable, two runs (the absolute addresses change with every start, the
   distances within one run show the regions).
2. The calculator as of tag `folge-28`, unpacked from git and extended by a few
   prints: where are the global symbol table, the function table, a tree node,
   the table of each call and the C stack of call()?

Run:  python addresses.py
Returns the values as dicts (for the scene) and prints them.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def build(source, target):
    subprocess.run(["cc", "-O0", "-o", str(target), str(source)], check=True)


def regions(runs=2):
    """One list per run: [{name: address}, …], one dict per call."""
    with tempfile.TemporaryDirectory() as tmp:
        prog = Path(tmp) / "regions"
        build(HERE / "regions.c", prog)
        result = []
        for _ in range(runs):
            out = subprocess.run([str(prog)], capture_output=True, text=True, check=True).stdout
            calls = []
            for line in out.splitlines():
                if line.startswith("call"):
                    calls.append({})
                elif m := re.match(r"\s+(\w+)\s+(\S+)\s+(0x[0-9a-f]+)", line):
                    calls[-1][m[2]] = int(m[3], 16)
            result.append(calls)
        return result


def record():
    with tempfile.TemporaryDirectory() as tmp:
        prog = Path(tmp) / "record"
        build(HERE / "record.c", prog)
        return subprocess.run([str(prog)], capture_output=True, text=True, check=True).stdout


# Additions to the calculator: (anchor in calc.y, text inserted after it)
PATCHES = [
    ("struct frame *frame = calloc(1, sizeof *frame);",
     '\n    if (getenv("ADDR")) fprintf(stderr, "frame %s heap %p size %zu c-stack %p\\n",'
     ' n->name, (void *)frame, sizeof *frame, (void *)&frame);'),
    ("struct node *n = calloc(1, sizeof *n);",
     '\n    if (getenv("ADDR") && kind == N_NUM) fprintf(stderr, "node heap %p\\n", (void *)n);'),
]
MAIN_ANCHOR = "int main("


def calculator(program="examples/factorial.calc", tag="folge-28"):
    """Runs the calculator with address prints; returns (stdout, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        d = tmp / "rechner"
        archive = subprocess.run(["git", "-C", str(REPO), "archive", tag, "rechner"], capture_output=True)
        if archive.returncode == 0:
            subprocess.run(["tar", "-x", "-C", str(tmp)], input=archive.stdout, check=True)
        else:
            # No such tag (public repository): the calculator in the root folder, two levels up;
            # `git checkout episode-29` gives exactly the one in the video.
            shutil.copytree(HERE.parent.parent, d, ignore=shutil.ignore_patterns("ir", "miniml", "optimizer", ".git"))
        y = (d / "calc.y").read_text()
        for anchor, addition in PATCHES:
            assert y.count(anchor) == 1, anchor
            y = y.replace(anchor, anchor + addition)
        # At start-up: global table and function table (static data)
        i = y.index("{", y.index(MAIN_ANCHOR)) + 1
        y = (y[:i] + '\n    if (getenv("ADDR")) fprintf(stderr, "code main %p\\nglobals static %p\\nfunctions static %p\\n",'
             ' (void *)main, (void *)&globals, (void *)functions);' + y[i:])
        (d / "calc.y").write_text(y)
        subprocess.run("yacc -d calc.y && lex calc.l && cc -o calc y.tab.c lex.yy.c",
                       shell=True, cwd=d, check=True, capture_output=True)
        run = subprocess.run(["./calc"], cwd=d, stdin=open(d / program),
                             capture_output=True, text=True, env={"ADDR": "1", "PATH": "/usr/bin:/bin"})
        return run.stdout, run.stderr


def main():
    for nr, run in enumerate(regions(), 1):
        code = run[0]["visit"]
        print(f"regions.c, run {nr}: visit at {code:#x}")
        for depth, a in enumerate(run, 1):
            print(f"  call {depth}: total {a['total'] - code:+#x}, calls {a['calls'] - code:+#x}, "
                  f"here {a['here']:#x} (distance to previous {a['here'] - run[max(depth - 2, 0)]['here']:+d}), "
                  f"box {a['*box']:#x} (distance {a['*box'] - run[max(depth - 2, 0)]['*box']:+d})")
        print(f"  free between box and here: {run[-1]['here'] - run[-1]['*box']:,} bytes")
    print(record())
    out, err = calculator()
    print("calculator stdout:", out.split())
    print(err)


if __name__ == "__main__":
    sys.exit(main())
