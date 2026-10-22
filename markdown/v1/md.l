%{
/* md.l: the scanner of a tiny Markdown-to-HTML translator. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "y.tab.h"

/* Copies text and replaces the characters HTML treats specially. */
char *escape(const char *s) {
    char *out = malloc(6 * strlen(s) + 1), *p = out;
    for (; *s; s++) {
        if      (*s == '<') p += sprintf(p, "&lt;");
        else if (*s == '>') p += sprintf(p, "&gt;");
        else if (*s == '&') p += sprintf(p, "&amp;");
        else *p++ = *s;
    }
    *p = '\0';
    return out;
}

/* Is a ** or a * open? Then the next one closes it. */
int strong_open = 0, em_open = 0;
%}
%option noyywrap
/* The scanner remembers where it is: at the start of a line (INITIAL),
 * inside a line (LINE), or inside `code`, where stars are just characters. */
%x LINE CODE

%%
"## "           { BEGIN(LINE); yylval.level = 2; return HEADING; }
"# "            { BEGIN(LINE); yylval.level = 1; return HEADING; }
"- "            { BEGIN(LINE); return ITEM; }
\n              { return BLANK; }
.               { yyless(0); BEGIN(LINE); /* ordinary line: read it again in LINE */ }

<LINE>"**"      { return STRONG; }
<LINE>"*"       { return EM; }
<LINE>"`"       { BEGIN(CODE); return TICK; }
<LINE>[^*`\n]+  { yylval.text = escape(yytext); return TEXT; }
<LINE>\n        { BEGIN(INITIAL); return NEWLINE; }

<CODE>[^`\n]+   { yylval.text = escape(yytext); return TEXT; }
<CODE>"`"       { BEGIN(LINE); return TICK; }
%%
