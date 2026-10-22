# frame main, depth 0, size 32
#   name     type      kind   size offset
#   x        int       var       4      0
#   y        int       var       4      4
#   t4       int       temp      4      8
#   t5       int       temp      4     12
#   t6       int       temp      4     16
#   t7       int       temp      4     20
#   t8       int       temp      4     24
# frame fact, depth 1, size 32
#   name     type      kind   size offset
#   n        int       param     4     16
#   t1       int       temp      4     20
#   t2       int       temp      4     24
#   t3       int       temp      4     28
    goto main
fact:
    if n <= 1 goto L1
    goto L2
L1:
    return 1
L2:
    t1 := n - 1
    param t1
    t2 := call fact, 1
    t3 := n * t2
    return t3
main:
    t4 := 2 * 3
    t5 := 10 + t4
    x := t5
    param 5
    t6 := call fact, 1
    print t6
    t7 := x / 4
    param t7
    t8 := call fact, 1
    y := t8
