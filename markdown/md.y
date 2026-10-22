%{
/* md.y: the parser. Every rule returns its piece of HTML as a string. */
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>

int yylex(void);
void yyerror(const char *s) { fprintf(stderr, "error: %s\n", s); }

/* Like printf, but into a new string: glues the HTML pieces together. */
char *html(const char *format, ...) {
    char *s;
    va_list args;
    va_start(args, format);
    vasprintf(&s, format, args);
    va_end(args);
    return s;
}
%}

%union {
    char *text;   /* text and the HTML built from it */
    int   level;  /* 1 for #, 2 for ## */
}

%token <text>  TEXT
%token <level> HEADING
%token ITEM BLANK STRONG_OPEN STRONG_CLOSE EM_OPEN EM_CLOSE TICK NEWLINE

%type <text> blocks block items item lines inline piece

/* Five shift/reduce conflicts: a list or paragraph can keep growing or end.
 * Shift (keep growing) is what we want, so we tell yacc to expect them. */
%expect 5

%%

document : blocks                    { printf("%s", $1); }
         ;

blocks   : /* empty */               { $$ = ""; }
         | blocks block              { $$ = html("%s%s", $1, $2); }
         ;

block    : HEADING inline NEWLINE    { $$ = html("<h%d>%s</h%d>\n", $1, $2, $1); }
         | items                     { $$ = html("<ul>\n%s</ul>\n", $1); }
         | lines                     { $$ = html("<p>%s</p>\n", $1); }
         | BLANK                     { $$ = ""; }
         ;

items    : items item                { $$ = html("%s%s", $1, $2); }
         | item
         ;

item     : ITEM inline NEWLINE       { $$ = html("<li>%s</li>\n", $2); }
         ;

lines    : lines inline NEWLINE      { $$ = html("%s\n%s", $1, $2); }
         | inline NEWLINE            { $$ = $1; }
         ;

inline   : inline piece              { $$ = html("%s%s", $1, $2); }
         | piece
         ;

piece    : TEXT
         | STRONG_OPEN inline STRONG_CLOSE { $$ = html("<strong>%s</strong>", $2); }
         | EM_OPEN inline EM_CLOSE         { $$ = html("<em>%s</em>", $2); }
         | TICK TEXT TICK            { $$ = html("<code>%s</code>", $2); }
         ;

%%
int main(void) { return yyparse(); }
