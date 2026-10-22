# frame main, depth 0, size 24
#   name     type      kind   size offset
#   x        int       var       4      0
#   y        int       var       4      4
#   t2       int       temp      4      8
#   t3       int       temp      4     12
#   t4       int       temp      4     16
# frame twice, depth 1, size 24
#   name     type      kind   size offset
#   a        int       param     4     16
#   t1       int       temp      4     20
    goto main
twice:
    t1 := a * 2
    return t1
main:
    t2 := 2 * 3
    t3 := 10 + t2
    x := t3
    param x
    t4 := call twice, 1
    y := t4
