/* ================================================================
 * PART 1: DECLARATIONS
 * Everything between %{ and %} is copied verbatim into y.tab.c.
 *
 * From here on, the parser no longer computes while it reads.
 * A loop body is read once but runs many times, a function body
 * only runs when it's called, and one branch of an if never runs.
 * So every rule builds a node of a tree, and the tree is run
 * afterwards.
 *
 * Besides int and float variables there are one-dimensional arrays:
 * int a[10] declares one, a[i] reads an element, a[i] = ... writes one.
 * Conditions can be combined with and, or, not; like in C, the right
 * side of and/or is only evaluated when it still matters.
 *
 * The tree can also be translated instead of run: ./calc -t prints
 * three-address code, ./calc -s the symbol tables with sizes and
 * offsets (the translator is in tac.c, included at the end of this file).
 * ================================================================ */
%{
#include <stdio.h>    /* for printf and fprintf */
#include <stdlib.h>   /* for calloc and free */
#include <string.h>   /* for strcmp */
#include "value.h"    /* struct value: a number together with its type */

/* yylex() is the lexer function that lex generates in lex.yy.c. */
int yylex(void);

/* Called by the parser when the input doesn't fit the grammar. */
void yyerror(const char *s) {
    fprintf(stderr, "error: %s\n", s);
}

/* ---------------------------------------------------------------
 * The tree: one node per expression or statement.
 * --------------------------------------------------------------- */
enum kind { N_NUM, N_VAR, N_INDEX, N_BINOP, N_COMPARE, N_CALL,        /* expressions */
            N_AND, N_OR, N_NOT,                                     /* conditions  */
            N_ASSIGN, N_DECL, N_IF, N_WHILE, N_RETURN, N_EXPR };    /* statements  */

struct node {
    enum kind kind;
    int    op;            /* + - * /  or  < > L(<=) G(>=) E(==) N(!=) */
    struct value val;     /* N_NUM: the number */
    char  *name;          /* variable or function name */
    int    type;          /* declared variables and parameters */
    int    len;           /* declared arrays: number of elements (0: no array) */
    struct node *a, *b, *c;  /* operands; or condition, then-block, else-block;
                                N_ASSIGN: a = value, b = index (only for a[i] = ...) */
    struct node *next;    /* the next statement in a block, the next argument */
};

struct node *node(enum kind kind, struct node *a, struct node *b, struct node *c) {
    struct node *n = calloc(1, sizeof *n);
    n->kind = kind; n->a = a; n->b = b; n->c = c;
    return n;
}

/* Appends n to the end of the list that starts at list. */
struct node *append(struct node *list, struct node *n) {
    if (!list) return n;
    if (!n) return list;
    struct node *p = list;
    while (p->next) p = p->next;
    p->next = n;
    return list;
}

/* ---------------------------------------------------------------
 * Symbol tables: one for the globals, and a new one for every
 * function call (its parameters and local variables).
 * --------------------------------------------------------------- */
struct entry {
    char  *name;
    int    type;       /* T_INT or T_FLOAT */
    int    has_value;  /* 0 after "int a", 1 after the first assignment */
    double num;
    int    len;        /* arrays only: number of elements */
    double *elems;     /* arrays only: the elements (start as 0) */
};
struct frame {
    struct entry vars[50];
    int n;
};
struct frame globals;
struct frame *current = &globals;   /* the table of the running call */

const char *type_name(int t) { return t == T_INT ? "int" : "float"; }

struct entry *find(struct frame *f, const char *name) {
    for (int i = 0; i < f->n; i++)
        if (strcmp(f->vars[i].name, name) == 0)
            return &f->vars[i];
    return NULL;
}

/* A name is looked up in the current call first, then among the globals. */
struct entry *lookup(const char *name) {
    struct entry *e = find(current, name);
    return e ? e : find(&globals, name);
}

struct entry *insert(char *name, int type) {
    struct entry *e = &current->vars[current->n++];
    e->name = name; e->type = type; e->has_value = 0;
    e->len = 0; e->elems = NULL;
    return e;
}

/* ---------------------------------------------------------------
 * Functions: only at the top level, as in C.
 * --------------------------------------------------------------- */
struct function {
    char  *name;
    int    type;            /* result type */
    struct node *params;    /* N_VAR nodes with name and type */
    struct node *body;      /* the statements, as a tree, run at every call */
};
struct function functions[50];
int nfunctions = 0;

struct function *find_function(const char *name) {
    for (int i = 0; i < nfunctions; i++)
        if (strcmp(functions[i].name, name) == 0)
            return &functions[i];
    return NULL;
}

/* ---------------------------------------------------------------
 * Running the tree: eval() for expressions (returns a value),
 * execute() for statements.
 * --------------------------------------------------------------- */
struct value error_value = { T_ERROR, 0 };
int show_calls = 0;             /* ./calc -c prints every call and return */
int depth = 0;                  /* how many calls are running */
int echo = 0;                   /* print "x = 16" for this assignment */
int returning = 0;              /* set by return, stops the statements of a call */
struct value return_value;

struct value eval(struct node *n);
void run(struct node *list);

/* + - * / with types, as before: int op int gives int, everything else float. */
struct value arith(struct value a, int op, struct value b) {
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
        if (r.type == T_INT) r.num = (long) r.num;   /* 10 / 4 = 2 */
        break;
    }
    return r;
}

/* A comparison is an int: 1 for true, 0 for false. */
struct value compare(struct value a, int op, struct value b) {
    struct value r = { T_INT, 0 };
    if (a.type == T_ERROR || b.type == T_ERROR)
        return error_value;
    switch (op) {
    case '<': r.num = a.num <  b.num; break;
    case '>': r.num = a.num >  b.num; break;
    case 'L': r.num = a.num <= b.num; break;
    case 'G': r.num = a.num >= b.num; break;
    case 'E': r.num = a.num == b.num; break;
    case 'N': r.num = a.num != b.num; break;
    }
    return r;
}

/* a[i]: finds the array and computes the index; the index is put
 * into *index. NULL (with a message) if something is wrong. */
struct entry *element(const char *name, struct node *index_expr, struct value *index) {
    struct entry *e = lookup(name);
    if (!e) {
        fprintf(stderr, "error: %s is not declared\n", name);
        return NULL;
    }
    if (!e->len) {
        fprintf(stderr, "error: %s is not an array\n", name);
        return NULL;
    }
    *index = eval(index_expr);
    if (index->type == T_ERROR) return NULL;
    if (index->type != T_INT) {
        fprintf(stderr, "error: index of %s must be int\n", name);
        return NULL;
    }
    if (index->num < 0 || index->num >= e->len) {
        fprintf(stderr, "error: index %g out of range for %s\n", index->num, name);
        return NULL;
    }
    return e;
}

/* Stores v in e; int into float is fine, float into int is an error. */
int store(struct entry *e, struct value v) {
    if (v.type == T_ERROR)
        return 0;
    if (e->type == T_INT && v.type == T_FLOAT) {
        fprintf(stderr, "error: cannot assign float to int %s\n", e->name);
        return 0;
    }
    e->num = v.num;
    e->has_value = 1;
    return 1;
}

/* A call: compute the arguments, give the call its own symbol table,
 * run the body, and hand back the value of return. */
struct value call(struct node *n) {
    struct function *f = find_function(n->name);
    if (!f) {
        fprintf(stderr, "error: %s is not a function\n", n->name);
        return error_value;
    }
    /* A new symbol table for this call: parameters and locals live here. */
    struct frame *frame = calloc(1, sizeof *frame);
    struct node *p = f->params, *arg = n->a;
    for (; p && arg; p = p->next, arg = arg->next) {
        struct value v = eval(arg);          /* arguments are computed in the caller's table */
        struct frame *caller = current;
        current = frame;
        int ok = store(insert(p->name, p->type), v);   /* same type check as an assignment */
        current = caller;
        if (!ok) { free(frame); return error_value; }
    }
    if (p || arg) {
        fprintf(stderr, "error: wrong number of arguments for %s\n", n->name);
        free(frame);
        return error_value;
    }
    if (show_calls) {
        printf("%*scall %s(", 2 * depth, "", n->name);
        for (int i = 0; i < frame->n; i++)
            printf("%s%s = %g", i ? ", " : "", frame->vars[i].name, frame->vars[i].num);
        printf(")\n");
    }
    depth++;
    struct frame *caller = current;
    current = frame;
    returning = 0;
    return_value = error_value;
    run(f->body);
    returning = 0;
    current = caller;
    free(frame);                             /* the locals are gone again */
    depth--;
    if (show_calls && return_value.type != T_ERROR)
        printf("%*sreturn %g\n", 2 * depth, "", return_value.num);

    struct value r = return_value;
    if (r.type == T_FLOAT && f->type == T_INT) {
        fprintf(stderr, "error: %s must return int\n", n->name);
        return error_value;
    }
    if (r.type == T_INT && f->type == T_FLOAT)
        r.type = T_FLOAT;
    return r;
}

/* Computes the value of an expression tree. */
struct value eval(struct node *n) {
    struct entry *e;
    struct value v;
    switch (n->kind) {
    case N_NUM:
        return n->val;
    case N_VAR:
        e = lookup(n->name);
        if (!e) {
            fprintf(stderr, "error: %s is not declared\n", n->name);
            return error_value;
        }
        if (e->len) {
            fprintf(stderr, "error: %s is an array\n", n->name);
            return error_value;
        }
        if (!e->has_value) {
            fprintf(stderr, "error: %s has no value yet\n", n->name);
            return error_value;
        }
        v.type = e->type; v.num = e->num;
        return v;
    case N_BINOP:
        return arith(eval(n->a), n->op, eval(n->b));
    case N_COMPARE:
        return compare(eval(n->a), n->op, eval(n->b));
    case N_CALL:
        return call(n);
    case N_INDEX:                        /* a[i] */
        e = element(n->name, n->a, &v);
        if (!e) return error_value;
        v.type = e->type; v.num = e->elems[(int) v.num];
        return v;
    case N_AND:                          /* b only if a is true */
        v = eval(n->a);
        if (v.type == T_ERROR || v.num == 0) return v;
        return eval(n->b);
    case N_OR:                           /* b only if a is false */
        v = eval(n->a);
        if (v.type == T_ERROR || v.num != 0) return v;
        return eval(n->b);
    case N_NOT:
        v = eval(n->a);
        if (v.type != T_ERROR) v.num = (v.num == 0);
        return v;
    default:
        return error_value;
    }
}

/* Runs one statement. */
void execute(struct node *n) {
    struct entry *e;
    struct value v;
    switch (n->kind) {
    case N_ASSIGN: {
        int show = echo;
        echo = 0;
        if (n->b) {                            /* a[i] = value */
            struct value i;
            if (!(e = element(n->name, n->b, &i))) break;
            v = eval(n->a);
            if (v.type == T_ERROR) break;
            if (e->type == T_INT && v.type == T_FLOAT) {
                fprintf(stderr, "error: cannot assign float to int %s\n", e->name);
                break;
            }
            e->elems[(int) i.num] = v.num;
            if (show)
                printf("%s[%g] = %g\n", n->name, i.num, v.num);
            break;
        }
        v = eval(n->a);
        if (v.type == T_ERROR) break;
        e = lookup(n->name);
        if (!e) e = insert(n->name, v.type);   /* first assignment declares it, in the current table */
        if (e->len) {
            fprintf(stderr, "error: %s is an array\n", n->name);
            break;
        }
        if (store(e, v) && show)
            printf("%s = %g\n", n->name, e->num);
        break;
    }
    case N_DECL:
        for (n = n->a; n; n = n->next) {
            if (find(current, n->name))
                fprintf(stderr, "error: %s is already declared\n", n->name);
            else if ((e = insert(n->name, n->type)) && n->len) {   /* an array */
                e->len = n->len;
                e->elems = calloc(n->len, sizeof(double));
            }
        }
        break;
    case N_IF:
        v = eval(n->a);
        if (v.type == T_ERROR) break;
        if (v.num != 0) run(n->b);
        else            run(n->c);
        break;
    case N_WHILE:
        for (;;) {
            v = eval(n->a);                    /* check the condition */
            if (v.type == T_ERROR || v.num == 0) break;
            run(n->b);                         /* run the body */
            if (returning) break;
        }                                      /* and start over */
        break;
    case N_RETURN:
        return_value = eval(n->a);
        returning = 1;
        break;
    case N_EXPR:
        eval(n->a);
        break;
    default:
        break;
    }
}

/* Runs a list of statements, until a return. */
void run(struct node *list) {
    for (; list && !returning; list = list->next)
        execute(list);
}

/* With -t or -s nothing runs; the statements of the top level
 * are collected and translated at the end (see tac.c). */
int translate = 0;
struct node *main_statements = NULL;

/* A statement typed at the top level runs right away, as before. */
void top_level(struct node *n) {
    if (!n) return;
    if (translate) {
        main_statements = append(main_statements, n);
        return;
    }
    if (n->kind == N_RETURN) {
        fprintf(stderr, "error: return outside a function\n");
        return;
    }
    if (n->kind == N_EXPR) {             /* a bare expression: print its value */
        struct value v = eval(n->a);
        if (v.type != T_ERROR) printf("%g\n", v.num);
        return;
    }
    echo = (n->kind == N_ASSIGN);
    execute(n);
    echo = 0;
}
%}

/* %union: the kinds of values a token or a rule can carry along.
 * New: op for the comparisons, and node for everything the rules build. */
%union {
    struct value val;   /* NUMBER: type and value, e.g. int 10 */
    char  *name;        /* IDENT: the name */
    int    type;        /* TYPE: T_INT or T_FLOAT */
    int    op;          /* COMPARE: which comparison */
    struct node *node;  /* the rules: a node of the tree */
}

%token <val>  NUMBER     /* a number, e.g. 10 (int) or 2.5 (float) */
%token <name> IDENT      /* a name, its text is in yylval.name     */
%token <type> TYPE       /* the keyword int or float               */
%token <op>   COMPARE    /* == != <= >= < >                         */
%token PLUS MINUS ASSIGN NEWLINE TIMES DIVIDE LPAREN RPAREN COMMA /* no value */
%token LBRACE RBRACE IF ELSE WHILE RETURN                         /* no value */
%token LBRACKET RBRACKET AND OR NOT                               /* no value */

/* Every rule now delivers a node instead of a value. */
%type  <node> statement statements block names params param_list args arg_list
%type  <node> condition cond_term cond_factor expr term factor name

/* ================================================================
 * PART 2: GRAMMAR RULES
 * The C code in { } still runs while reducing, but it only builds
 * the tree; nothing is computed yet.
 * ================================================================ */
%%

/* A program: statements and functions, in any order. A statement
 * at the top level runs as soon as its line is complete. */
program : /* empty */
        | program statement   { top_level($2); }
        | program function
        ;

/* Functions only at the top level, never inside each other.
 * "int fact(int n) { ... }": result type, name, parameters, body. */
function : TYPE IDENT LPAREN params RPAREN block NEWLINE
             { struct function *f = &functions[nfunctions++];
               f->name = $2; f->type = $1; f->params = $4; f->body = $6; }
         ;

params     : /* empty */                  { $$ = NULL; }
           | param_list
           ;
param_list : param_list COMMA TYPE IDENT  { struct node *p = node(N_VAR, 0, 0, 0);
                                            p->name = $4; p->type = $3; $$ = append($1, p); }
           | TYPE IDENT                   { $$ = node(N_VAR, 0, 0, 0); $$->name = $2; $$->type = $1; }
           ;

/* What used to be a line is now a statement. The end of a line ends it.
 * Braces are required, and else stays on the line of the closing brace,
 * so it's always clear which if an else belongs to: no dangling else. */
statement : IDENT ASSIGN expr NEWLINE     { $$ = node(N_ASSIGN, $3, 0, 0); $$->name = $1; }
          | IDENT LBRACKET expr RBRACKET ASSIGN expr NEWLINE
                                          { $$ = node(N_ASSIGN, $6, $3, 0); $$->name = $1; }
          | TYPE names NEWLINE            { $$ = node(N_DECL, $2, 0, 0); }
          | IF LPAREN condition RPAREN block NEWLINE
                                          { $$ = node(N_IF, $3, $5, 0); }
          | IF LPAREN condition RPAREN block ELSE block NEWLINE
                                          { $$ = node(N_IF, $3, $5, $7); }
          | WHILE LPAREN condition RPAREN block NEWLINE
                                          { $$ = node(N_WHILE, $3, $5, 0); }
          | RETURN expr NEWLINE           { $$ = node(N_RETURN, $2, 0, 0); }
          | expr NEWLINE                  { $$ = node(N_EXPR, $1, 0, 0); }
          | NEWLINE                       { $$ = NULL; }
          ;

/* A block: "{", end of line, any number of statements, "}". */
block      : LBRACE NEWLINE statements RBRACE  { $$ = $3; }
           ;
statements : /* empty */                  { $$ = NULL; }
           | statements statement         { $$ = append($1, $2); }
           ;

/* The declared type sits on the stack just left of names: $<type>0.
 * A name is a variable or an array: "int i, a[10]". */
names   : names COMMA name   { $$ = append($1, $3); $3->type = $<type>0; }
        | name               { $$ = $1; $$->type = $<type>0; }
        ;
name    : IDENT              { $$ = node(N_VAR, 0, 0, 0); $$->name = $1; }
        | IDENT LBRACKET NUMBER RBRACKET
                             { $$ = node(N_VAR, 0, 0, 0); $$->name = $1;
                               if ($3.type != T_INT || $3.num < 1)
                                   fprintf(stderr, "error: size of %s must be a positive int\n", $1);
                               $$->len = $3.type == T_INT && $3.num >= 1 ? (int) $3.num : 1; }
        ;

/* Comparisons only in conditions, so expr, term and factor stay as they were.
 * or, and, not with the usual precedence (not before and before or),
 * built like expr, term, factor. No parentheses around conditions. */
condition   : condition OR cond_term     { $$ = node(N_OR, $1, $3, 0); }
            | cond_term
            ;
cond_term   : cond_term AND cond_factor  { $$ = node(N_AND, $1, $3, 0); }
            | cond_factor
            ;
cond_factor : NOT cond_factor            { $$ = node(N_NOT, $2, 0, 0); }
            | expr COMPARE expr          { $$ = node(N_COMPARE, $1, $3, 0); $$->op = $2; }
            ;

/* The same rules as before, only the actions build nodes:
 * before:  $$ = arith($1, '+', $3);   (a value)
 * now:     a node N_BINOP with the two operands as children. */
expr : expr MINUS term   { $$ = node(N_BINOP, $1, $3, 0); $$->op = '-'; }
     | expr PLUS term    { $$ = node(N_BINOP, $1, $3, 0); $$->op = '+'; }
     | term
     ;

term : term TIMES factor   { $$ = node(N_BINOP, $1, $3, 0); $$->op = '*'; }
     | term DIVIDE factor  { $$ = node(N_BINOP, $1, $3, 0); $$->op = '/'; }
     | factor
     ;

/* A call and an array element can go anywhere a number can. */
factor : NUMBER                     { $$ = node(N_NUM, 0, 0, 0); $$->val = $1; }
       | IDENT                      { $$ = node(N_VAR, 0, 0, 0); $$->name = $1; }
       | IDENT LPAREN args RPAREN   { $$ = node(N_CALL, $3, 0, 0); $$->name = $1; }
       | IDENT LBRACKET expr RBRACKET
                                    { $$ = node(N_INDEX, $3, 0, 0); $$->name = $1; }
       | LPAREN expr RPAREN         { $$ = $2; }
       ;

args     : /* empty */          { $$ = NULL; }
         | arg_list
         ;
arg_list : arg_list COMMA expr  { $$ = append($1, $3); }
         | expr
         ;

%%
/* ================================================================
 * PART 3: ADDITIONAL C CODE
 * ================================================================ */

/* The translator into three-address code. */
#include "tac.c"

int main(int argc, char **argv) {
    int show_code = 0, show_symbols = 0;
    /* Unbuffered stdout, so that our output and the error messages
     * (stderr) appear in the right order. */
    setbuf(stdout, NULL);
    /* ./calc -c (or ./run.sh -c): print every call and return.
     * ./calc -t prints three-address code, ./calc -s the symbol
     * tables; both together print the tables first. */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-c") == 0) show_calls = 1;
        else if (strcmp(argv[i], "-t") == 0) show_code = 1;
        else if (strcmp(argv[i], "-s") == 0) show_symbols = 1;
    }
    translate = show_code || show_symbols;
#if YYDEBUG
    /* Only when compiled with -DYYDEBUG=1 (./run.sh -d). */
    yydebug = 1;
#endif
    int status = yyparse();
    if (status == 0 && translate)
        status = translate_program(show_symbols, show_code);
    return status;
}
