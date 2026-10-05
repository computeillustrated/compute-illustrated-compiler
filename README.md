# compute-illustrated-compiler

A small calculator built with lex and yacc that grows, episode by episode, into a tiny compiler.
It is the running example of the YouTube channel **Compute Illustrated**: every video shows what
this code really does, and every episode has a tag with the code exactly as it is in the video.

## Run it

You need `lex` (flex), `yacc` (bison) and a C compiler.

```bash
./run.sh                 # interactive: type a line like  x = 10 + 2 * 3
./run.sh -d input.txt    # with the parser's trace; the parser states go to y.output
./stack.sh "x = 1 + 2 * 3"   # walks you through the shift/reduce steps
```

## Episodes

| Episode | Video | Tag |
|---|---|---|
| 1 | How does a compiler work? The six phases, step by step | `episode-01` |
| 2 | Compiler vs interpreter vs JIT: what linker and loader do | `episode-02` |
| 3 | How does a lexer work? Tokens, regular expressions and finite automata | `episode-03` |
| 4 | Regex to NFA to DFA: Thompson's and the subset construction | `episode-04` |
| 5 | How to write a lexer by hand: from state diagram to code | `episode-05` |
| 6 | Lex and flex explained: generate a lexer from regular expressions | `episode-06` |
| 7 | Why regex can't match nested parentheses (pumping lemma) | `episode-07` |
| 8 | What is a context-free grammar? Derivations, parse trees, ambiguity | `episode-08` |
| 9 | How does a top-down parser work? Backtracking, step by step | `episode-09` |
| 10 | How to remove left recursion from a grammar (and left factoring) | `episode-10` |
| 11 | What is an LL(1) grammar? Lookahead instead of backtracking | `episode-11` |
| 12 | How to compute FIRST and FOLLOW sets, round by round | `episode-12` |

To see the code of one episode: `git checkout episode-04`

## License

MIT, see [LICENSE](LICENSE).
