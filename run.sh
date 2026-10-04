#!/bin/bash
# Rebuilds lexer and parser and starts the calculator.
# Usage:  ./run.sh                 -> interactive (type your input, end with Ctrl+D)
#         ./run.sh input.txt       -> reads the input from a file
#         ./run.sh -d [file]       -> the same with the parser's yydebug trace;
#                                     the parser states are written to y.output
set -e
cd "$(dirname "$0")"

DEBUG=""
if [ "$1" = "-d" ]; then
    DEBUG="-DYYDEBUG=1"
    shift
fi

if [ -n "$DEBUG" ]; then
    yacc -d -v calc.y              # -v also writes the state table to y.output
else
    yacc -d calc.y                 # parser: calc.y -> y.tab.c + y.tab.h
fi
lex calc.l                         # lexer:  calc.l -> lex.yy.c
cc $DEBUG -o calc y.tab.c lex.yy.c # compile both together

if [ -n "$1" ]; then
    ./calc < "$1"
else
    ./calc
fi
