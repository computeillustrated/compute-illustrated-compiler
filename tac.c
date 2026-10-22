/* ================================================================
 * Translating the tree into three-address code.
 * Included at the end of calc.y, so it sees the tree (struct node),
 * the functions (functions[]) and the top-level statements.
 *
 *   ./calc -t < prog.calc    the three-address code
 *   ./calc -s < prog.calc    the symbol tables: name, type, kind,
 *                            size and offset of every variable
 *
 * The scheme: every expression has a place, the name that holds its
 * value: a number, a variable, or a new temporary t1, t2, ...
 * Its code is printed before the code that uses the place. Jumps go
 * to new labels L1, L2, ...; a condition gets two labels, where to go
 * when it is true and where to go when it is false.
 *
 * Sizes as in a classic 32-bit layout: int and float 4 bytes each,
 * aligned to 4; an array has n * 4 bytes, rounded up to a multiple
 * of 8, aligned to 8. The top level gets offsets from 0. A function
 * frame starts with 16 bytes of bookkeeping (result, saved pc, saved
 * depth, saved display), so parameters start at offset 16. After the
 * variables come the temporaries.
 * ================================================================ */
#include <stdarg.h>   /* for putcode(fmt, ...) */

/* ---------------------------------------------------------------
 * Symbol tables: one per frame (the top level, every function).
 * --------------------------------------------------------------- */
enum sym_kind { S_VAR, S_PARAM, S_TEMP };
struct sym {
    char *name;
    int   type;      /* T_INT or T_FLOAT; for arrays the element type */
    int   kind;      /* S_VAR, S_PARAM, S_TEMP */
    int   len;       /* arrays: number of elements, else 0 */
    int   size;      /* bytes */
    int   offset;    /* bytes from the start of the frame */
};
struct scope {
    char *name;          /* "main" for the top level, else the function */
    int   depth;         /* 0 for the top level, 1 for a function */
    struct sym syms[200];
    int   n;
    int   offset;        /* next free offset */
    int   has_vars;      /* declared or assigned variables (not parameters) */
};
struct scope scopes[51];
int nscopes = 0;
struct scope *main_scope;
struct scope *scope;            /* the frame we're translating */
struct function *function_now;  /* NULL at the top level */
int tac_errors = 0;

int align_up(int m, int n) { return m % n ? m + n - m % n : m; }

void tac_error(const char *msg, const char *name) {
    fprintf(stderr, "error: ");
    fprintf(stderr, msg, name);
    fprintf(stderr, "\n");
    tac_errors++;
}

struct sym *find_sym(struct scope *s, const char *name) {
    for (int i = 0; i < s->n; i++)
        if (strcmp(s->syms[i].name, name) == 0)
            return &s->syms[i];
    return NULL;
}

/* As in the calculator: first the running function, then the top level.
 * Temporaries of the top level are not visible inside a function. */
struct sym *find_name(const char *name) {
    struct sym *s = find_sym(scope, name);
    if (!s && scope != main_scope) {
        s = find_sym(main_scope, name);
        if (s && s->kind == S_TEMP) s = NULL;
    }
    return s;
}

struct sym *enter_sym(struct scope *s, char *name, int type, int kind, int len) {
    struct sym *e = &s->syms[s->n++];
    int alignment = len ? 8 : 4;
    e->name = name; e->type = type; e->kind = kind; e->len = len;
    e->size = len ? align_up(4 * len, 8) : 4;
    s->offset = align_up(s->offset, alignment);
    e->offset = s->offset;
    s->offset += e->size;
    if (kind == S_VAR) s->has_vars = 1;
    return e;
}

/* t1, t2, ... and L1, L2, ... are counted over the whole program. */
int ntemps = 0, nlabels = 0;

/* "t3" is a temporary, "L3" a label: a variable with such a name
 * would be mistaken for one of them. */
int reserved(const char *name) {
    if ((name[0] != 't' && name[0] != 'L') || !name[1]) return 0;
    for (const char *p = name + 1; *p; p++)
        if (*p < '0' || *p > '9') return 0;
    return 1;
}

char *newtemp(int type) {
    char buf[16];
    snprintf(buf, sizeof buf, "t%d", ++ntemps);
    return enter_sym(scope, strdup(buf), type, S_TEMP, 0)->name;
}
int newlabel(void) { return ++nlabels; }

/* ---------------------------------------------------------------
 * The code: one line per instruction or label, printed at the end.
 * --------------------------------------------------------------- */
char *code[5000];
int ncode = 0;

void putcode(const char *fmt, ...) {
    char buf[200];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    code[ncode++] = strdup(buf);
}
void putlabel(int l) { putcode("L%d:", l); }

const char *cop_name(int op) {
    switch (op) {
    case 'L': return "<=";
    case 'G': return ">=";
    case 'E': return "==";
    case 'N': return "!=";
    case '<': return "<";
    default:  return ">";
    }
}

/* A number as a place: a float always keeps its point (4.0, not 4). */
char *constant(struct value v) {
    char buf[40];
    snprintf(buf, sizeof buf, v.type == T_INT ? "%.0f" : "%g", v.num);
    if (v.type == T_FLOAT && !strpbrk(buf, ".e")) strcat(buf, ".0");
    return strdup(buf);
}

/* int -> float: a conversion is an instruction of its own. */
char *widen(char *place, int from, int to) {
    if (from == T_INT && to == T_FLOAT) {
        char *t = newtemp(T_FLOAT);
        putcode("%s := inttofloat %s", t, place);
        return t;
    }
    return place;
}

/* ---------------------------------------------------------------
 * Pass 1: which variables does a frame have? Goes through the
 * statements in order, like the calculator would run them: a
 * declaration enters its names, a first assignment its target.
 * --------------------------------------------------------------- */
int type_of(struct node *n);

void collect(struct node *list) {
    for (struct node *n = list; n; n = n->next) {
        switch (n->kind) {
        case N_DECL:
            for (struct node *d = n->a; d; d = d->next) {
                if (reserved(d->name)) tac_error("%s is reserved for temporaries and labels", d->name);
                else if (find_sym(scope, d->name)) tac_error("%s is already declared", d->name);
                else enter_sym(scope, d->name, d->type, S_VAR, d->len);
            }
            break;
        case N_ASSIGN:
            if (!n->b && !find_name(n->name)) {
                if (reserved(n->name)) tac_error("%s is reserved for temporaries and labels", n->name);
                else enter_sym(scope, n->name, type_of(n->a), S_VAR, 0);
            }
            break;
        case N_IF:
            collect(n->b);
            collect(n->c);
            break;
        case N_WHILE:
            collect(n->b);
            break;
        default:
            break;
        }
    }
}

/* The type of an expression, without producing code (needed in pass 1). */
int type_of(struct node *n) {
    struct sym *s;
    struct function *f;
    switch (n->kind) {
    case N_NUM:   return n->val.type;
    case N_VAR:
    case N_INDEX: return (s = find_name(n->name)) ? s->type : T_INT;
    case N_CALL:  return (f = find_function(n->name)) ? f->type : T_INT;
    case N_BINOP: return type_of(n->a) == T_INT && type_of(n->b) == T_INT ? T_INT : T_FLOAT;
    default:      return T_INT;
    }
}

/* ---------------------------------------------------------------
 * Pass 2: code. gen_expr returns the place of an expression and
 * its type; the code for it is already printed.
 * --------------------------------------------------------------- */
char *gen_expr(struct node *n, int *type);

/* a[i]: the byte offset of the element, 4 * i, in a new temporary. */
char *gen_offset(char *name, struct node *index, struct sym **array) {
    int t;
    struct sym *s = find_name(name);
    if (!s) { tac_error("%s is not declared", name); return "?"; }
    if (!s->len) { tac_error("%s is not an array", name); return "?"; }
    *array = s;
    char *i = gen_expr(index, &t);
    if (t != T_INT) tac_error("index of %s must be int", name);
    char *offset = newtemp(T_INT);
    putcode("%s := 4 * %s", offset, i);
    return offset;
}

/* p(e1, ..., en): first the code for all arguments, then all params,
 * so that a call inside an argument can't mix up the params. */
char *gen_call(struct node *n, int *type, int want_result) {
    struct function *f = find_function(n->name);
    char *places[20];
    int count = 0, t;
    if (!f) { tac_error("%s is not a function", n->name); *type = T_INT; return "?"; }
    struct node *p = f->params, *arg = n->a;
    for (; p && arg; p = p->next, arg = arg->next) {
        char *place = gen_expr(arg, &t);
        if (t == T_FLOAT && p->type == T_INT)
            tac_error("cannot pass float to int %s", p->name);
        places[count++] = widen(place, t, p->type);
    }
    if (p || arg) tac_error("wrong number of arguments for %s", n->name);
    for (int i = 0; i < count; i++)
        putcode("param %s", places[i]);
    *type = f->type;
    if (!want_result) {
        putcode("call %s, %d", f->name, count);
        return NULL;
    }
    char *result = newtemp(f->type);
    putcode("%s := call %s, %d", result, f->name, count);
    return result;
}

char *gen_expr(struct node *n, int *type) {
    struct sym *s;
    int ta, tb;
    char *a, *b, *t;
    switch (n->kind) {
    case N_NUM:
        *type = n->val.type;
        return constant(n->val);
    case N_VAR:
        s = find_name(n->name);
        if (!s) { tac_error("%s is not declared", n->name); *type = T_INT; return n->name; }
        if (s->len) tac_error("%s is an array", n->name);
        *type = s->type;
        return n->name;
    case N_INDEX:
        s = NULL;
        a = gen_offset(n->name, n->a, &s);
        *type = s ? s->type : T_INT;
        t = newtemp(*type);
        putcode("%s := %s[%s]", t, n->name, a);
        return t;
    case N_BINOP:
        a = gen_expr(n->a, &ta);
        b = gen_expr(n->b, &tb);
        *type = (ta == T_INT && tb == T_INT) ? T_INT : T_FLOAT;
        a = widen(a, ta, *type);
        b = widen(b, tb, *type);
        t = newtemp(*type);
        putcode("%s := %s %c %s", t, a, n->op, b);
        return t;
    case N_CALL:
        return gen_call(n, type, 1);
    default:
        tac_error("%s", "a condition is only allowed in if and while");
        *type = T_INT;
        return "?";
    }
}

/* A condition jumps: to yes if it is true, to no if it is false. */
void gen_cond(struct node *n, int yes, int no) {
    int ta, tb;
    char *a = gen_expr(n->a, &ta);
    char *b = gen_expr(n->b, &tb);
    a = widen(a, ta, ta == T_INT && tb == T_INT ? T_INT : T_FLOAT);
    b = widen(b, tb, ta == T_INT && tb == T_INT ? T_INT : T_FLOAT);
    putcode("if %s %s %s goto L%d", a, cop_name(n->op), b, yes);
    putcode("goto L%d", no);
}

void gen_statements(struct node *list);

void gen_statement(struct node *n) {
    struct sym *s;
    int t, yes, no, next, start;
    char *place, *offset;
    switch (n->kind) {
    case N_ASSIGN:
        if (n->b) {                                /* a[i] := value */
            s = NULL;
            offset = gen_offset(n->name, n->b, &s);
            place = gen_expr(n->a, &t);
        } else {
            s = find_name(n->name);
            offset = NULL;
            place = gen_expr(n->a, &t);
            if (s && s->len) tac_error("%s is an array", n->name);
        }
        if (!s) break;
        if (s->type == T_INT && t == T_FLOAT)
            tac_error("cannot assign float to int %s", n->name);
        place = widen(place, t, s->type);
        if (offset) putcode("%s[%s] := %s", n->name, offset, place);
        else        putcode("%s := %s", n->name, place);
        break;
    case N_DECL:
        break;                                     /* only the symbol table */
    case N_IF:
        yes = newlabel(); no = newlabel();
        next = n->c ? newlabel() : 0;
        gen_cond(n->a, yes, no);
        putlabel(yes);
        gen_statements(n->b);
        if (n->c) {
            putcode("goto L%d", next);
            putlabel(no);
            gen_statements(n->c);
            putlabel(next);
        } else
            putlabel(no);
        break;
    case N_WHILE:
        start = newlabel(); yes = newlabel(); no = newlabel();
        putlabel(start);
        gen_cond(n->a, yes, no);
        putlabel(yes);
        gen_statements(n->b);
        putcode("goto L%d", start);
        putlabel(no);
        break;
    case N_RETURN:
        if (!function_now) { tac_error("%s", "return outside a function"); break; }
        place = gen_expr(n->a, &t);
        if (t == T_FLOAT && function_now->type == T_INT)
            tac_error("%s must return int", function_now->name);
        putcode("return %s", widen(place, t, function_now->type));
        break;
    case N_EXPR:
        if (n->a->kind == N_CALL && function_now) {   /* a call whose result nobody uses */
            gen_call(n->a, &t, 0);
            break;
        }
        place = gen_expr(n->a, &t);
        if (!function_now)                         /* at the top level the calculator prints it */
            putcode("print %s", place);
        break;
    default:
        break;
    }
}

void gen_statements(struct node *list) {
    for (; list; list = list->next)
        gen_statement(list);
}

/* ---------------------------------------------------------------
 * Output
 * --------------------------------------------------------------- */
void print_scope(struct scope *s) {
    printf("# frame %s, depth %d, size %d\n", s->name, s->depth, align_up(s->offset, 8));
    printf("#   %-8s %-9s %-6s %4s %6s\n", "name", "type", "kind", "size", "offset");
    for (int i = 0; i < s->n; i++) {
        struct sym *e = &s->syms[i];
        char type[20];
        if (e->len) snprintf(type, sizeof type, "%s[%d]", type_name(e->type), e->len);
        else        snprintf(type, sizeof type, "%s", type_name(e->type));
        printf("#   %-8s %-9s %-6s %4d %6d\n", e->name, type,
               e->kind == S_VAR ? "var" : e->kind == S_PARAM ? "param" : "temp", e->size, e->offset);
    }
}

/* The variables of a frame come first; like a block of declarations
 * they end on a multiple of 8. The temporaries come after them. */
void end_of_variables(struct scope *s) {
    if (s->has_vars) s->offset = align_up(s->offset, 8);
}

int translate_program(int show_symbols, int show_code) {
    /* Pass 1: variables of the top level, then of every function. */
    main_scope = scope = &scopes[nscopes++];
    main_scope->name = "main";
    collect(main_statements);
    end_of_variables(main_scope);
    for (int i = 0; i < nfunctions; i++) {
        struct function *f = &functions[i];
        struct scope *s = scope = &scopes[nscopes++];
        if (strcmp(f->name, "main") == 0) tac_error("%s is the name of the top level", f->name);
        s->name = f->name; s->depth = 1;
        s->offset = 16;                     /* result, saved pc, depth, display */
        for (struct node *p = f->params; p; p = p->next)
            enter_sym(s, p->name, p->type, S_PARAM, 0);
        collect(f->body);
        end_of_variables(s);
    }
    /* Pass 2: the code. Functions first, the top level last; the
     * first instruction jumps over the functions. */
    if (nfunctions) putcode("goto main");
    for (int i = 0; i < nfunctions; i++) {
        struct node *last = NULL;
        function_now = &functions[i];
        scope = &scopes[i + 1];
        putcode("%s:", function_now->name);
        gen_statements(function_now->body);
        for (struct node *p = function_now->body; p; p = p->next) last = p;
        if (!last || last->kind != N_RETURN)
            putcode("return");
    }
    function_now = NULL;
    scope = main_scope;
    if (nfunctions) putcode("main:");
    gen_statements(main_statements);
    if (tac_errors) return 1;

    if (show_symbols)
        for (int i = 0; i < nscopes; i++)
            print_scope(&scopes[i]);
    if (show_code)
        for (int i = 0; i < ncode; i++)
            printf(code[i][strlen(code[i]) - 1] == ':' ? "%s\n" : "    %s\n", code[i]);
    return 0;
}
