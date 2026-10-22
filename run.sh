#!/bin/bash
# Rebuilds lexer and parser and starts the calculator.
# Usage:  ./run.sh                 -> interactive (type your input, end with Ctrl+D)
#         ./run.sh input.txt       -> reads the input from a file
#         ./run.sh -d [file]       -> the same with the parser's yydebug trace;
#                                     the parser states are written to y.output
#         ./run.sh -c [file]       -> prints every function call and return
#         ./run.sh -t [file]       -> prints three-address code instead of running
#         ./run.sh -s [file]       -> prints the symbol tables (sizes and offsets)
# -t and -s can be combined: ./run.sh -s -t file
set -e

DEBUG=""
OPTIONS=()
while [[ "$1" == -? ]]; do
    case "$1" in
        -d) DEBUG="-DYYDEBUG=1" ;;
        *)  OPTIONS+=("$1") ;;
    esac
    shift
done
INPUT=""
if [ -n "$1" ]; then
    INPUT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"   # before cd: relative paths keep working
fi
cd "$(dirname "$0")"

if [ -n "$DEBUG" ]; then
    yacc -d -v calc.y              # -v also writes the state table to y.output
else
    yacc -d calc.y                 # parser: calc.y -> y.tab.c + y.tab.h
fi
lex calc.l                         # lexer:  calc.l -> lex.yy.c
cc $DEBUG -o calc y.tab.c lex.yy.c # compile both together (y.tab.c includes tac.c)

if [ -n "$INPUT" ]; then
    ./calc "${OPTIONS[@]}" < "$INPUT"
else
    ./calc "${OPTIONS[@]}"
fi
