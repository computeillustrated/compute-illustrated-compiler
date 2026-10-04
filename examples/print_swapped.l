%{
#include <stdio.h>
%}
%option noyywrap
letter   [a-zA-Z]
digit    [0-9]
%%
{letter}+    { printf("<IDENT, \"%s\">\n", yytext); }
"print"      { printf("<PRINT>\n"); }
{digit}+     { printf("<NUMBER, \"%s\">\n", yytext); }
[ \t\n]      { /* skip */ }
.            { printf("unknown character: %s\n", yytext); }
%%
int main(void) {
    yylex();
    return 0;
}

/* The same rules as print.l, but with lines 8 and 9 swapped. flex warns
   that the "print" rule cannot be matched: the rule for names comes
   first and matches print just as long, so print is now just a name.
   Build:  lex print_swapped.l && cc -o print lex.yy.c && echo "print x" | ./print */
