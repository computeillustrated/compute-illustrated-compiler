"""A scanner for the calculator, written by hand from a state diagram.

It produces the same tokens as the scanner that lex generates from calc.l.
Every state of the diagram becomes one case, every edge an if, and every
star (put characters back) a retract.

Usage:  python3 hand_scanner.py < input.txt
        echo "x = 10.5 + 2 * 3" | python3 hand_scanner.py
"""
import sys

DIGITS = "0123456789"
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
SINGLE = {"+": "PLUS", "-": "MINUS", "*": "TIMES", "/": "DIVIDE",
          "=": "ASSIGN", "(": "LPAREN", ")": "RPAREN", "\n": "NEWLINE"}
END = "\0"      # marks the end of the buffer

buffer = ""     # the input, followed by END
start = 0       # first character of the current lexeme
pos = 0         # next character to read


def next_char():
    """Returns the character at pos and moves pos forward."""
    global pos
    pos += 1
    return buffer[pos - 1]


def retract(n):
    """Moves pos back by n characters."""
    global pos
    pos -= n


def next_token():
    global start
    state = 0
    while True:
        match state:
            case 0:
                start = pos
                c = next_char()
                if c in DIGITS:    state = 1
                elif c in LETTERS: state = 6
                elif c in " \t":   state = 0       # skip
                elif c in SINGLE:  return SINGLE[c], c
                elif c == END:     return None
                else: print("unknown character:", c, file=sys.stderr)
            case 1:
                c = next_char()
                if c in DIGITS:    state = 1
                elif c == ".":     state = 2
                else:              state = 4
            case 2:
                c = next_char()
                if c in DIGITS:    state = 3
                else:              state = 5
            case 3:
                c = next_char()
                if c in DIGITS:    state = 3
                else:              state = 4
            case 4:
                retract(1)
                return "NUMBER", buffer[start:pos]
            case 5:
                retract(2)
                return "NUMBER", buffer[start:pos]
            case 6:
                c = next_char()
                if c in LETTERS or c in DIGITS: state = 6
                else:              state = 7
            case 7:
                retract(1)
                return "IDENT", buffer[start:pos]


def scan(text):
    """Yields the tokens of text as (name, lexeme) pairs, one after another."""
    global buffer, pos
    buffer, pos = text + END, 0
    while (token := next_token()) is not None:
        yield token


if __name__ == "__main__":
    # Same output format as calc.l: <NUMBER, "10">
    for name, lexeme in scan(sys.stdin.read()):
        shown = "\\n" if lexeme == "\n" else lexeme
        print(f'<{name}, "{shown}">', flush=True)
