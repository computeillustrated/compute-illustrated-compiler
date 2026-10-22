/* A value together with its type. Shared by calc.l and calc.y:
 * the lexer fills it in for every number, the parser computes with it. */
#define T_INT   1
#define T_FLOAT 2
#define T_ERROR 3   /* after a semantic error, so that it is reported only once */

struct value {
    int    type;    /* T_INT, T_FLOAT or T_ERROR */
    double num;     /* the value itself; for T_INT always a whole number */
};
