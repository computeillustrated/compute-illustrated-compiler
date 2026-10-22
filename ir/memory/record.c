/* Episode 29: records with alignment. A smaller version of the calculator's
 * symbol table entry, once in an unfavourable and once in a favourable field
 * order, plus an array of them. */
#include <stdio.h>
#include <stddef.h>

struct entry {           /* fields in the order you might write them */
    char   type;
    double num;
    char   has_value;
};

struct entry_sorted {    /* the same fields, largest first */
    double num;
    char   type;
    char   has_value;
};

int main(void) {
    printf("sizeof char %zu, double %zu, int %zu, pointer %zu\n",
           sizeof(char), sizeof(double), sizeof(int), sizeof(void *));
    printf("alignof double %zu\n", _Alignof(double));
    printf("entry: type %zu, num %zu, has_value %zu, size %zu\n",
           offsetof(struct entry, type), offsetof(struct entry, num),
           offsetof(struct entry, has_value), sizeof(struct entry));
    printf("entry_sorted: num %zu, type %zu, has_value %zu, size %zu\n",
           offsetof(struct entry_sorted, num), offsetof(struct entry_sorted, type),
           offsetof(struct entry_sorted, has_value), sizeof(struct entry_sorted));

    struct entry vars[3];
    for (int i = 0; i < 3; i++)
        printf("vars[%d] at +%td\n", i, (char *)&vars[i] - (char *)&vars[0]);
    return 0;
}
