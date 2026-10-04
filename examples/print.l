%{
#include <stdio.h>
%}
%option noyywrap
letter   [a-zA-Z]
digit    [0-9]
%%
"print"      { printf("<PRINT>\n"); }
{letter}+    { printf("<IDENT, \"%s\">\n", yytext); }
{digit}+     { printf("<NUMBER, \"%s\">\n", yytext); }
[ \t\n]      { /* skip */ }
.            { printf("unknown character: %s\n", yytext); }
%%
int main(void) {
    yylex();
    return 0;
}

/* A keyword with its own rule: "print" comes before the rule for names.
   On a tie (same length), lex picks the earlier rule, so print is a
   keyword, but printer is still a name (the longest match comes first).
   Build:  lex print.l && cc -o print lex.yy.c && echo "print x" | ./print */
