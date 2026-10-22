/* ================================================================
 * PART 1: DECLARATIONS
 * Everything between %{ and %} is copied verbatim into y.tab.c.
 * ================================================================ */
%{
#include <stdio.h>    /* for printf and fprintf */
#include <stdlib.h>   /* for free */
#include <string.h>   /* for strcmp */
#include "value.h"    /* struct value: a number together with its type */

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

/* ---------------------------------------------------------------
 * The symbol table: every name the program has seen so far,
 * with its type and (once assigned) its value.
 * --------------------------------------------------------------- */
struct entry {
    char  *name;
    int    type;       /* T_INT or T_FLOAT */
    int    has_value;  /* 0 after "int a", 1 after the first assignment */
    double num;
};
struct entry table[100];
int entries = 0;

const char *type_name(int t) { return t == T_INT ? "int" : "float"; }

struct entry *lookup(const char *name) {
    for (int i = 0; i < entries; i++)
        if (strcmp(table[i].name, name) == 0)
            return &table[i];
    return NULL;
}

struct entry *insert(char *name, int type) {
    struct entry *e = &table[entries++];
    e->name = name;
    e->type = type;
    e->has_value = 0;
    printf("  symbol     %s : %s\n", name, type_name(type));
    return e;
}

/* A declaration like "int a, b, c" enters each name with the given type. */
void declare(char *name, int type) {
    if (lookup(name)) {
        fprintf(stderr, "error: %s is already declared\n", name);
        return;
    }
    insert(name, type);
}

/* After an error, expressions carry T_ERROR, so that one mistake
 * produces exactly one message. */
struct value error_value = { T_ERROR, 0 };

/* Reading a variable: it must be declared and have a value. */
struct value use(char *name) {
    struct entry *e = lookup(name);
    if (!e) {
        fprintf(stderr, "error: %s is not declared\n", name);
        return error_value;
    }
    if (!e->has_value) {
        fprintf(stderr, "error: %s has no value yet\n", name);
        return error_value;
    }
    struct value v = { e->type, e->num };
    return v;
}

/* + - * / with types: int op int gives int, everything else float.
 * So 10 / 4 is 2 (whole-number division), but 10 / 4.0 is 2.5. */
struct value arith(struct value a, char op, struct value b) {
    struct value r;
    if (a.type == T_ERROR || b.type == T_ERROR)
        return error_value;
    r.type = (a.type == T_INT && b.type == T_INT) ? T_INT : T_FLOAT;
    switch (op) {
    case '+': r.num = a.num + b.num; break;
    case '-': r.num = a.num - b.num; break;
    case '*': r.num = a.num * b.num; break;
    case '/':
        if (b.num == 0) {
            fprintf(stderr, "error: division by zero\n");
            return error_value;
        }
        r.num = a.num / b.num;
        if (r.type == T_INT)
            r.num = (long) r.num;   /* drop the remainder: 10 / 4 = 2 */
        break;
    }
    return r;
}

/* "x = expr": the first assignment declares x with the type of expr.
 * An int fits into a float variable, a float doesn't fit into an int. */
void assign(char *name, struct value v) {
    if (v.type == T_ERROR)
        return;
    struct entry *e = lookup(name);
    if (!e)
        e = insert(name, v.type);
    else if (e->type == T_INT && v.type == T_FLOAT) {
        fprintf(stderr, "error: cannot assign float to int %s\n", name);
        return;
    }
    e->num = v.num;      /* int into float: the number stays the same */
    e->has_value = 1;
    printf("%s = %g\n", name, e->num);
}
%}

/* %union defines which kinds of values a token or a rule can
 * "carry along". A NUMBER token carries its value and its type,
 * an IDENT token its text, e.g. "x", a TYPE token int or float.
 * From this, y.tab.h gets the data type YYSTYPE and the variable yylval,
 * into which the lexer writes the values (yylval.val, yylval.name, ...). */
%union {
    struct value val;  /* numbers and expressions: type and value, e.g. int 10 */
    char  *name;       /* variable names */
    int    type;       /* the type in a declaration: T_INT or T_FLOAT */
}

/* %token declares the token types the lexer may return.
 * yacc gives each one a number and writes it to y.tab.h,
 * so that calc.l can write e.g. "return NUMBER;".
 * <val>, <name> or <type> says which field of the union holds the value. */
%token <val>  NUMBER     /* a number, e.g. 10 (int) or 2.5 (float) */
%token <name> IDENT      /* a name, its text is in yylval.name     */
%token <type> TYPE       /* the keyword int or float               */
%token PLUS MINUS ASSIGN NEWLINE TIMES DIVIDE LPAREN RPAREN COMMA /* no value */

/* %type says: the rules expr, term and factor produce a value as well,
 * namely a number with its type (the result of the calculation). */
%type  <val>  expr
%type  <val>  term
%type  <val>  factor

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

/* A line is an assignment like "x = 1 + 2", a declaration like
 * "int a, b", or an empty line (just pressing Enter shouldn't be an error). */
line    : IDENT ASSIGN expr NEWLINE
           {
             /* $1, $2, $3, ... are the values of the symbols in the rule,
              * counted from the left:
              *   $1 = IDENT      -> the text "x"
              *   $2 = ASSIGN     -> has no value
              *   $3 = expr       -> the result with its type, e.g. int 16
              *   $4 = NEWLINE    -> has no value                       */
             assign($1, $3);
           }
        | TYPE names NEWLINE
        | NEWLINE
        ;

/* The names in a declaration: "a", "a, b", "a, b, c", ...
 * The type isn't part of this rule, it comes from the left:
 * TYPE sits on the stack just before names, and $<type>0
 * reads the value right below $1, i.e. the int or float. */
names   : names COMMA IDENT  { declare($3, $<type>0); }
        | IDENT              { declare($1, $<type>0); }
        ;

/* The heart of it: an expression is either
 *   - an expression, then a plus or minus, then a term   (left-recursive!)
 *   - or simply a single term
 * A recursive-descent parser would loop forever here.
 * yacc works bottom-up, though, and has no problem with it. */
expr : expr MINUS term
         {
           printf("  reduce     expr   -> expr - term        (%g - %g = %g)\n", $1.num, $3.num, $1.num - $3.num);
           $$ = arith($1, '-', $3);
         }
     | expr PLUS term
         {
           /* $$ is the value this rule itself "returns".
            * $1 = the expression so far (e.g. int 10)
            * $2 = PLUS (no value)
            * $3 = the new term (e.g. int 6)
            * Result: 10 + 6 = 16 becomes the value of this expression. */
           printf("  reduce     expr   -> expr + term        (%g + %g = %g)\n", $1.num, $3.num, $1.num + $3.num);
           $$ = arith($1, '+', $3);
         }
     | term
         {
           /* Smallest case: a single term is already an
            * expression. Its value is simply the term's value. */
           printf("  reduce     expr   -> term               (%g)\n", $1.num);
           $$ = $1;
         }
     ;

term : term TIMES factor
        {printf("  reduce     term   -> term * factor      (%g * %g = %g)\n", $1.num, $3.num, $1.num * $3.num);
          $$ = arith($1, '*', $3);}
     | term DIVIDE factor
        {$$ = arith($1, '/', $3);
          printf("  reduce     term   -> term / factor      (%g / %g = %g)\n", $1.num, $3.num, $$.num);}
     | factor
        {printf("  reduce     term   -> factor             (%g)\n", $1.num);$$ = $1;}
     ;

/* A factor is a number, a variable (looked up in the symbol table)
 * or an expression in parentheses. */
factor : NUMBER {printf("  reduce     factor -> NUMBER             (%g)\n", $1.num);$$ = $1;}
       | IDENT  {$$ = use($1);
                 printf("  reduce     factor -> IDENT              (%s = %g)\n", $1, $$.num);}
       | LPAREN expr RPAREN {printf("  reduce     factor -> ( expr )           (%g)\n", $2.num);$$ = $2;}
       ;

%%
/* ================================================================
 * PART 3: ADDITIONAL C CODE
 * Also copied verbatim to the end of y.tab.c.
 * ================================================================ */

int main(void) {
    /* Unbuffered stdout, so that our printf output and the error
     * messages (stderr) appear in the right order. */
    setbuf(stdout, NULL);
#if YYDEBUG
    /* Only when compiled with -DYYDEBUG=1 (./run.sh -d):
     * the parser prints every step (state, shift, reduce, stack). */
    yydebug = 1;
#endif
    /* yyparse() is the parser generated by yacc.
     * Internally it calls yylex() again and again, fetches tokens
     * and checks them against the grammar above.
     * Returns 0 = everything ok, 1 = syntax error. */
    return yyparse();
}
