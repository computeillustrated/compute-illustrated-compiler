%{
#include <stdio.h>
#include <string.h>
int is_keyword(const char *word);
%}
%option noyywrap
letter   [a-zA-Z]
digit    [0-9]
%%
{letter}+    { if (is_keyword(yytext)) printf("<PRINT>\n");
               else printf("<IDENT, \"%s\">\n", yytext); }
{digit}+     { printf("<NUMBER, \"%s\">\n", yytext); }
[ \t\n]      { /* skip */ }
.            { printf("unknown character: %s\n", yytext); }
%%
/* Only one rule for all names; its action looks the word up in a table. */
static const char *keywords[] = { "print" };

int is_keyword(const char *word) {
    for (size_t i = 0; i < sizeof keywords / sizeof keywords[0]; i++)
        if (strcmp(word, keywords[i]) == 0)
            return 1;
    return 0;
}

int main(void) {
    yylex();
    return 0;
}
