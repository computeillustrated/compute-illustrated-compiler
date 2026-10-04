/* ================================================================
 * PART 1: DECLARATIONS
 * Everything between %{ and %} is copied verbatim into y.tab.c.
 * ================================================================ */
%{
#include <stdio.h>    /* for printf and fprintf */
#include <stdlib.h>   /* for free */

/* yylex() is the lexer function that lex generates in lex.yy.c.
 * The parser calls it every time it needs the next token.
 * Only declared here so the C compiler knows about it. */
int yylex(void);

/* The parser calls yyerror() automatically when the input
 * doesn't fit the grammar, e.g. for "x = + 2".
 * This function MUST exist, otherwise nothing compiles. */
void yyerror(const char *s) {
    fprintf(stderr, "error: %s\n", s);
}
%}

/* %union defines which kinds of values a token or a rule can
 * "carry along". A NUMBER token carries its value, e.g. 1,
 * an IDENT token its text, e.g. "x".
 * From this, y.tab.h gets the data type YYSTYPE and the variable yylval,
 * into which the lexer writes the values (yylval.num, yylval.name). */
%union {
    int   num;    /* for numbers */
    char *name;   /* for variable names */
}

/* %token declares the token types the lexer may return.
 * yacc gives each one a number and writes it to y.tab.h,
 * so that calc.l can write e.g. "return NUMBER;".
 * <num> or <name> says which field of the union holds the value. */
%token <num>  NUMBER      /* a number, its value is in yylval.num  */
%token <name> IDENT      /* a name, its text is in yylval.name    */
%token PLUS MINUS ASSIGN NEWLINE TIMES DIVIDE LPAREN RPAREN /* these tokens carry no value */

/* %type says: the rule "expr" produces a value as well,
 * namely a number (the result of the calculation). */
%type  <num>  expr
%type  <num>  term
%type  <num>  factor

/* ================================================================
 * PART 2: GRAMMAR RULES
 * Every rule looks like:   name : alternative1 | alternative2 ;
 * The C code in { } runs as soon as the rule has been
 * recognized completely (this is called "reducing").
 * ================================================================ */
%%

/* The FIRST rule is automatically the start symbol.
 * A program is either empty, or a program followed by one more
 * line. That is left-recursive and simply means: any number of lines. */
program : /* empty */
         | program line
         ;

/* A line is either an assignment like "x = 1 + 2" followed by a newline,
 * or an empty line (just pressing Enter shouldn't be an error). */
line    : IDENT ASSIGN expr NEWLINE
           {
             /* $1, $2, $3, ... are the values of the symbols in the rule,
              * counted from the left:
              *   $1 = IDENT      -> the text "x"
              *   $2 = ASSIGN    -> has no value
              *   $3 = expr  -> the result of the calculation, e.g. 3
              *   $4 = NEWLINE   -> has no value                       */
             printf("%s = %d\n", $1, $3);

             /* The lexer copied the name with strdup(),
              * so we free that memory here. */
             free($1);
           }
         | NEWLINE
         ;

/* The heart of it: an expression is either
 *   - an expression, then a plus or minus, then a term   (left-recursive!)
 *   - or simply a single term
 * A recursive-descent parser would loop forever here.
 * yacc works bottom-up, though, and has no problem with it. */
expr : expr MINUS term
      	   {
              printf("  reduce     expr   -> expr - term        (%d - %d = %d)\n", $1, $3, $1 - $3);
      	     $$ = $1 - $3;
      	   }

      	 | expr PLUS term
           {
             /* $$ is the value this rule itself "returns".
              * $1 = the expression so far (e.g. 1)
              * $2 = PLUS (no value)
              * $3 = the new term (e.g. 2)
              * Result: 1 + 2 = 3 becomes the value of this expression. */
            printf("  reduce     expr   -> expr + term        (%d + %d = %d)\n", $1, $3, $1 + $3);
             $$ = $1 + $3;
           }
         | term
           {
             /* Smallest case: a single term is already an
              * expression. Its value is simply the term's value. */
            printf("  reduce     expr   -> term               (%d)\n", $1);
             $$ = $1;
           }
         ;

term : term TIMES factor
        {printf("  reduce     term   -> term * factor      (%d * %d = %d)\n", $1, $3, $1 * $3);
          $$ = $1 * $3;}
      | term DIVIDE factor
        {printf("  reduce     term   -> term / factor      (%d / %d = %d)\n", $1, $3, $1 / $3);$$ = $1 / $3;}
      | factor
        {printf("  reduce     term   -> factor             (%d)\n", $1);$$ = $1;}

factor : NUMBER {printf("  reduce     factor -> NUMBER             (%d)\n", $1);$$ = $1;}
      | LPAREN expr RPAREN {printf("  reduce     factor -> ( expr )           (%d)\n", $2);$$ = $2;}

%%
/* ================================================================
 * PART 3: ADDITIONAL C CODE
 * Also copied verbatim to the end of y.tab.c.
 * ================================================================ */

int main(void) {
    /* yyparse() is the parser generated by yacc.
     * Internally it calls yylex() again and again, fetches tokens
     * and checks them against the grammar above.
     * Returns 0 = everything ok, 1 = syntax error. */
#if YYDEBUG
    /* Only when compiled with -DYYDEBUG=1 (./run.sh -d):
     * the parser prints every step (state, shift, reduce, stack). */
    yydebug = 1;
    /* Unbuffered stdout, so that our printf output lands in the right
     * place between the trace lines (which go to stderr). */
    setbuf(stdout, NULL);
#endif
    return yyparse();
}
