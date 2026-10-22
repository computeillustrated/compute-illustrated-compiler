"""Episode 29: a heap in miniature, with first fit and best fit.

The heap is a row of cells. Used blocks and holes alternate; freeing a block
merges it with neighbouring holes. For a request, the strategy picks the hole:
  first fit: the first one that is big enough
  best fit:  the smallest one that is big enough
If none fits, the request fails (in a real program the heap would grow until
it runs into the stack).

Run:  python heap.py
"""

SIZE = 16

# Our own sequence of requests and frees: ("alloc", name, cells) or ("free", name)
STEPS = [
    ("alloc", "a", 3),
    ("alloc", "b", 4),
    ("alloc", "c", 2),
    ("alloc", "d", 5),
    ("free", "a"),
    ("free", "c"),
    ("alloc", "e", 2),
    ("alloc", "f", 3),
]

# Continuation for first fit after f failed: free b, the holes merge
MORE = [
    ("free", "b"),
    ("alloc", "f", 3),
]


# Counterexample: best fit is not always better. After the frees, holes of 5 and
# 4 cells remain; best fit leaves a single cell each for e and f, and g (2 cells)
# fails, while first fit places all three.
COUNTER = [
    ("alloc", "a", 5),
    ("alloc", "b", 2),
    ("alloc", "c", 4),
    ("alloc", "d", 5),
    ("free", "a"),
    ("free", "c"),
    ("alloc", "e", 3),
    ("alloc", "f", 4),
    ("alloc", "g", 2),
]


class Heap:
    def __init__(self, size, strategy):
        self.size = size
        self.strategy = strategy
        self.blocks = {}            # name -> (start, length)

    def holes(self):
        """[(start, length)] of the free pieces, left to right (already merged)."""
        used = sorted(self.blocks.values())
        free, pos = [], 0
        for start, length in used:
            if start > pos:
                free.append((pos, start - pos))
            pos = start + length
        if pos < self.size:
            free.append((pos, self.size - pos))
        return free

    def alloc(self, name, length):
        fitting = [h for h in self.holes() if h[1] >= length]
        if not fitting:
            return None
        if self.strategy == "first fit":
            start = fitting[0][0]
        elif self.strategy == "best fit":
            start = min(fitting, key=lambda h: (h[1], h[0]))[0]
        else:
            raise ValueError(self.strategy)
        self.blocks[name] = (start, length)
        return start

    def free(self, name):
        del self.blocks[name]

    def cells(self):
        """A string with one character per cell: the block's name or '.'."""
        c = ["."] * self.size
        for name, (start, length) in self.blocks.items():
            c[start:start + length] = name * length
        return "".join(c)


def simulate(strategy, steps=STEPS, size=SIZE):
    """[(step, result, cells)] for every step."""
    h = Heap(size, strategy)
    log = []
    for step in steps:
        if step[0] == "alloc":
            result = h.alloc(step[1], step[2])
        else:
            h.free(step[1])
            result = None
        log.append((step, result, h.cells()))
    return log


if __name__ == "__main__":
    for strategy, steps in (("first fit", STEPS + MORE), ("best fit", STEPS),
                            ("first fit (counterexample)", COUNTER), ("best fit (counterexample)", COUNTER)):
        print(strategy)
        for step, result, cells in simulate(strategy.split(" (")[0], steps):
            text = " ".join(map(str, step))
            if step[0] == "alloc":
                text += f" -> {'failed' if result is None else f'at {result}'}"
            print(f"  {cells}  {text}")
