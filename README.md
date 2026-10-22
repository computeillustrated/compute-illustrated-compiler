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

From episode 27 on, `markdown/` holds a second translator built with the same tools: a tiny
Markdown to HTML (`markdown/run.sh` translates `markdown/README.md`; `markdown/v1/` is the first
version with its 13 conflicts).

From episode 28 on, the calculator is a small language (comparisons, `if`/`else`, `while`, blocks,
functions with recursion); `./run.sh -c` shows the calls.
From episode 31 on, `./run.sh -t` prints three-address code instead of running the program, and
`./run.sh -s` prints the symbol tables with offsets.

`ir/` (from episode 29, Python): a machine that runs the calculator's three-address code, the intermediate representations (syntax tree, DAG, postfix, quadruples, triples), a stack machine and procedure frames. See `ir/README.md`.

`miniml/` (from episode 37, Python): Mini-ML, a tiny functional language with type inference, an interpreter with environments and closures, and the SECD machine. See `miniml/README.md`.

`optimizer/` (from episode 41, Python): basic blocks and flow graphs, local and loop optimizations, data-flow analysis, code generation with register allocation and a peephole optimizer, all working on the calculator's real three-address code. See `optimizer/README.md`.

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
| 13 | How a table-driven LL(1) parser works: parse table and stack | `episode-13` |
| 14 | How to write a recursive descent parser (one function per rule) | `episode-14` |
| 15 | How does a bottom-up parser work? Shift, reduce and the handle | `episode-15` |
| 16 | How a parser knows that * binds tighter than +: operator precedence | `episode-16` |
| 17 | How does an LR parser work? The automaton behind yacc and bison | `episode-17` |
| 18 | LR(0) items, closure and goto: building an SLR parse table | `episode-18` |
| 19 | LR(1) vs LALR(1): lookaheads in the items, and why yacc merges states | `episode-19` |
| 20 | How yacc and bison work: y.output, conflicts and %left | `episode-20` |
| 21 | LL vs LR parsing: which is more powerful, and why? | `episode-21` |
| 22 | Semantic analysis explained: errors a parser can't catch | `episode-22` |
| 23 | Attribute grammars explained: synthesized vs inherited attributes | `episode-23` |
| 24 | S-attributed vs L-attributed definitions and translation schemes, explained | `episode-24` |
| 25 | Syntax-directed translation with recursive descent: attributes as parameters | `episode-25` |
| 26 | Bottom-up translation in yacc: the value stack, mid-rule actions and $0 | `episode-26` |
| 27 | Build a Markdown to HTML translator with lex and yacc | `episode-27` |
| 28 | From calculator to programming language: if, while and functions with yacc | `episode-28` |
| 29 | Stack vs heap explained: where a running program keeps its variables | `episode-29` |
| 30 | Stack frames explained: control links, access links and the display | `episode-30` |
| 31 | Intermediate code explained: AST, DAG, postfix and three-address code | `episode-31` |
| 32 | How a stack machine runs code: postfix vs. three-address code, step by step | `episode-32` |
| 33 | How a compiler gives every variable an address: symbol tables, sizes and offsets | `episode-33` |
| 34 | Generating three-address code: temporaries, type conversions and array addresses | `episode-34` |
| 35 | How compilers translate if and while: jumps, labels and short-circuit evaluation | `episode-35` |
| 36 | How function calls are compiled: param, call, return and stack frames | `episode-36` |
| 37 | A first look at ML: functions are values | `episode-37` |
| 38 | Type inference: how a compiler finds types nobody wrote (unification, polymorphism) | `episode-38` |
| 39 | Interpreting Mini-ML: environments and closures | `episode-39` |
| 40 | The SECD machine: how functional code runs, closures and recursion | `episode-40` |
| 41 | Basic blocks and flow graphs: how a compiler sees the shape of your code | `episode-41` |
| 42 | Compiler optimization inside a basic block: constant folding, copy propagation, inlining and the DAG | `episode-42` |
| 43 | How compilers optimize loops: code motion, induction variables, unrolling and dead code | `episode-43` |

To see the code of one episode: `git checkout episode-04`

## License

MIT, see [LICENSE](LICENSE).
