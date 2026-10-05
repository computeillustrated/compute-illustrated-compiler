"""A parser for the calculator, written by hand as a recursive descent.

One function per nonterminal of the grammar without left recursion:

    program   -> line program | ε
    line      -> IDENT ASSIGN expr NEWLINE | NEWLINE
    expr      -> term expr_rest
    expr_rest -> MINUS term expr_rest | PLUS term expr_rest | ε
    term      -> factor term_rest
    term_rest -> TIMES factor term_rest | DIVIDE factor term_rest | ε
    factor    -> NUMBER | LPAREN expr RPAREN

Every if tests the lookahead set of one alternative. The rests receive the
value from the left, so 10 - 2 - 3 is computed as (10 - 2) - 3 = 5.
It prints the same lines as the calculator built with lex and yacc.

Usage:  echo "x = 10 - 2 - 3" | python3 descent.py
"""
import sys

from hand_scanner import scan

tokens = iter(())   # the scanner's tokens, one after another
lookahead = None    # name of the next token, "$" at the end of the input
lexeme = None       # its text


def advance():
    global lookahead, lexeme
    lookahead, lexeme = next(tokens, ("$", ""))


def match(name):
    """Compares the expected token with the next one, then moves on by one."""
    if lookahead != name:
        error()
    text = lexeme
    advance()
    return text


def error():
    print("error: syntax error", file=sys.stderr)
    sys.exit(1)


def program():
    if lookahead in ("IDENT", "NEWLINE"):
        line()
        program()
    elif lookahead in ("$",):
        pass
    else:
        error()


def line():
    if lookahead in ("IDENT",):
        name = match("IDENT")
        match("ASSIGN")
        value = expr()
        match("NEWLINE")
        print(f"{name} = {value:g}", flush=True)
    elif lookahead in ("NEWLINE",):
        match("NEWLINE")
    else:
        error()


def expr():
    left = term()
    return expr_rest(left)


def expr_rest(left):
    if lookahead in ("MINUS",):
        match("MINUS")
        return expr_rest(left - term())
    elif lookahead in ("PLUS",):
        match("PLUS")
        return expr_rest(left + term())
    elif lookahead in ("NEWLINE", "RPAREN"):
        return left
    else:
        error()


def term():
    left = factor()
    return term_rest(left)


def term_rest(left):
    if lookahead in ("TIMES",):
        match("TIMES")
        return term_rest(left * factor())
    elif lookahead in ("DIVIDE",):
        match("DIVIDE")
        return term_rest(left / factor())
    elif lookahead in ("MINUS", "NEWLINE", "PLUS", "RPAREN"):
        return left
    else:
        error()


def factor():
    if lookahead in ("NUMBER",):
        return float(match("NUMBER"))
    elif lookahead in ("LPAREN",):
        match("LPAREN")
        value = expr()
        match("RPAREN")
        return value
    else:
        error()


def parse(text):
    """Reads tokens from text and parses them, starting with the start symbol."""
    global tokens
    tokens = scan(text)
    advance()
    program()


if __name__ == "__main__":
    parse(sys.stdin.read())
