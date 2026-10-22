%{
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "value.h"    /* struct value, needed by y.tab.h */
#include "y.tab.h"

/* From here on, the scanner no longer prints every token: a program with
 * loops and functions would print hundreds of lines. ./run.sh -d still
 * shows every token the parser reads. */
%}
%option noyywrap

%%
[0-9]+         { yylval.val.type = T_INT;   yylval.val.num = atof(yytext); return NUMBER; }
[0-9]+\.[0-9]+ { yylval.val.type = T_FLOAT; yylval.val.num = atof(yytext); return NUMBER; }
"int"          { yylval.type = T_INT;   return TYPE; }
"float"        { yylval.type = T_FLOAT; return TYPE; }
"if"           { return IF; }
"else"         { return ELSE; }
"while"        { return WHILE; }
"return"       { return RETURN; }
    /* The keywords come BEFORE the rule for names: "while" matches both,
     * with the same length, and then the earlier rule wins.
     * "whiley" is longer as a name, so it stays an IDENT. */
[a-zA-Z][a-zA-Z0-9]* { yylval.name = strdup(yytext); return IDENT; }
"+"            { return PLUS; }
"-"            { return MINUS; }
"*"            { return TIMES; }
"/"            { return DIVIDE; }
    /* All six comparisons are one token; the value says which one.
     * The two-character ones come first only for readability:
     * flex takes the longest match anyway, so "<=" never becomes "<" "=". */
"=="           { yylval.op = 'E'; return COMPARE; }
"!="           { yylval.op = 'N'; return COMPARE; }
"<="           { yylval.op = 'L'; return COMPARE; }
">="           { yylval.op = 'G'; return COMPARE; }
"<"            { yylval.op = '<'; return COMPARE; }
">"            { yylval.op = '>'; return COMPARE; }
"="            { return ASSIGN; }
"("            { return LPAREN; }
")"            { return RPAREN; }
"{"            { return LBRACE; }
"}"            { return RBRACE; }
","            { return COMMA; }
\n             { return NEWLINE; }
[ \t]          { /* skip spaces and tabs */ }
.              { fprintf(stderr, "unknown character: %s\n", yytext); }
%%
