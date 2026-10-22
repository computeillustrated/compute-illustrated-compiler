%{
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "value.h"    /* struct value, needed by y.tab.h */
#include "y.tab.h"

/* Prints the recognized token and hands it to the parser. */
#define TOKEN(t) do { printf("<%s, \"%s\">\n", #t, *yytext == '\n' ? "\\n" : yytext); return t; } while (0)
%}
%option noyywrap

%%
[0-9]+         { yylval.val.type = T_INT;   yylval.val.num = atof(yytext); TOKEN(NUMBER); }
[0-9]+\.[0-9]+ { yylval.val.type = T_FLOAT; yylval.val.num = atof(yytext); TOKEN(NUMBER); }
"int"       { yylval.type = T_INT;   TOKEN(TYPE); }
"float"     { yylval.type = T_FLOAT; TOKEN(TYPE); }
[a-zA-Z][a-zA-Z0-9]* { yylval.name = strdup(yytext); TOKEN(IDENT); }
"+"         { TOKEN(PLUS); }
"-"	    	{ TOKEN(MINUS); }
"*"			{ TOKEN(TIMES);}
"/"			{ TOKEN(DIVIDE); }
"="         { TOKEN(ASSIGN); }
"("			{ TOKEN(LPAREN);}
")"			{ TOKEN(RPAREN);}
","			{ TOKEN(COMMA);}
\n          { TOKEN(NEWLINE); }
[ \t]       { /* skip spaces and tabs */ }
.           { fprintf(stderr, "unknown character: %s\n", yytext); }
%%
