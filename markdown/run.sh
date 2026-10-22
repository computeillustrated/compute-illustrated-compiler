#!/bin/bash
# Rebuilds the Markdown-to-HTML translator and runs it.
# Usage:  ./run.sh               -> translates README.md
#         ./run.sh file.md       -> translates the given file
#         ./run.sh < file.md     -> reads the input from stdin
set -e
INPUT="${1:-README.md}"
[ -n "$1" ] && INPUT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
cd "$(dirname "$0")"

yacc -d md.y                   # parser:  md.y -> y.tab.c + y.tab.h
lex md.l                       # scanner: md.l -> lex.yy.c
cc -o md y.tab.c lex.yy.c      # compile both together

if [ -t 0 ] || [ -n "$1" ]; then
    ./md < "$INPUT"
else
    ./md
fi
