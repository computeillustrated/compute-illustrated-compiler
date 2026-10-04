#!/bin/bash
# Walks you through the parser step by step, so you can draw the stack
# on paper along with it. Every step tells you what to write on top
# (SHIFT) or what to cross out and replace (REDUCE).
# Usage:  ./stack.sh "x = 1 + 2 * 3"
#         ./stack.sh                  -> asks for the input
cd "$(dirname "$0")"

input="$*"
if [ -z "$input" ]; then
    read -r -p "Input (e.g. x = 1 + 2 * 3): " input
fi

# Run the parser in debug mode and collect the complete trace.
# Our token output from calc.l (<NUMBER, "1">) and the "reduce" lines
# from calc.y end up in the middle of the trace and provide texts and values.
trace=$(./run.sh -d <(printf '%s\n' "$input") 2>&1)
if ! grep -q "^Starting parse" <<< "$trace"; then
    echo "$trace"
    echo "Build failed."
    exit 1
fi

stack=()        # the stack as symbols, e.g. "NUMBER[1]" or "term[2]"
lookahead=""    # last token read but not yet shifted
step=0

show_stack() {
    echo "  Stack (bottom -> top):  ${stack[*]:-(empty)}"
}

next() {
    echo
    read -r -p "  [Enter] next, q to quit " answer < /dev/tty
    [ "$answer" = "q" ] && exit 0
}

header() {
    step=$((step + 1))
    echo
    echo "── Step $step ─────────────────────────────────────────────"
    echo "  Lookahead:  ${lookahead:-(no token read yet)}"
}

echo
echo "Input: $input"
echo "Draw an empty stack. Bottom is on the left, top is on the right."
next

while IFS= read -r line; do
    # the lexer returns a token: <NUMBER, "1">
    if [[ $line =~ \<([A-Z]+),\ \"(.*)\"\> ]]; then
        name=${BASH_REMATCH[1]}; text=${BASH_REMATCH[2]}
        if [ "$name" = "NEWLINE" ]; then lookahead="NEWLINE"; else lookahead="$name[$text]"; fi

    elif [[ $line == "Reading a token: Now at end of input." ]]; then
        lookahead="END"

    elif [[ $line =~ ^Shifting\ token\ ([A-Z]+) ]]; then
        header
        echo "  SHIFT"
        echo "  Write on top:  $lookahead"
        stack+=("$lookahead")
        lookahead=""
        show_stack
        next

    elif [[ $line =~ ^Reducing\ stack ]]; then
        rhs=(); value=""; output=""

    elif [[ $line =~ ^\ +\$[0-9]+\ =\ (token|nterm)\ ([A-Za-z]+) ]]; then
        rhs+=("${BASH_REMATCH[2]}")

    elif [[ $line =~ ^\ \ reduce.*\(([^\(\)]*)\)[[:space:]]*$ ]]; then
        value=${BASH_REMATCH[1]}
        value=${value##*= }                 # "1 + 4 = 5" -> "5"

    elif [[ $line =~ ^-\>\ \$\$\ =\ nterm\ ([a-z]+) ]]; then
        lhs=${BASH_REMATCH[1]}
        n=${#rhs[@]}
        removed=("${stack[@]:${#stack[@]}-n}")
        stack=("${stack[@]:0:${#stack[@]}-n}")
        new="$lhs"; [ -n "$value" ] && new="$lhs[$value]"
        stack+=("$new")

        header
        echo "  REDUCE by rule:  $lhs -> ${rhs[*]:-(empty)}"
        if [ "$n" -eq 0 ]; then
            echo "  Cross out:       nothing (empty rule)"
        else
            echo "  Cross out top:   ${removed[*]}"
        fi
        echo "  Write instead:   $new"
        [ -n "$output" ] && echo "  Program prints:  $output"
        show_stack
        next

    elif [[ $line == "error: "* ]]; then
        header
        echo "  SYNTAX ERROR: with this lookahead, neither shift nor reduce fits."
        show_stack
        exit 1

    elif [[ $line == "Cleanup: popping nterm program ()" ]]; then
        header
        echo "  DONE: the input is used up, only program is left on the stack."
        echo "  The input is accepted."
        exit 0

    elif [[ ! $line =~ ^(Starting\ parse|Entering\ state|Stack\ now|Next\ token|Reading\ a\ token|Cleanup|Error:|\ \ reduce) ]]; then
        output="$line"                      # our own output, e.g. "x = 5"
    fi
done <<< "$trace"
