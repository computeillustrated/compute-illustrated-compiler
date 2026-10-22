/* Episode 29: where do variables with different lifetimes live?
 * Prints the addresses of the code, a global, a static local, a local and a
 * malloc'ed variable, for three nested calls.
 * Build and run: ./run.sh (in this folder). */
#include <stdio.h>
#include <stdlib.h>

int total = 0;                      /* global: lives for the whole run */

void visit(int depth) {
    static int calls = 0;           /* static local: lives for the whole run, visible only here */
    int here = depth;               /* local: one per call, gone after return */
    int *box = malloc(sizeof *box); /* dynamic: lives until free */
    *box = depth;
    calls++;
    total += depth;
    printf("call %d\n", depth);
    printf("  code    visit   %p\n", (void *)visit);
    printf("  static  total   %p\n", (void *)&total);
    printf("  static  calls   %p\n", (void *)&calls);
    printf("  stack   here    %p\n", (void *)&here);
    printf("  heap    *box    %p\n", (void *)box);
    if (depth < 3)
        visit(depth + 1);
    free(box);
}

int main(void) {
    visit(1);
    printf("total = %d\n", total);
    return 0;
}
