# frame main, depth 0, size 32
#   name     type      kind   size offset
#   debug    int       var       4      0
#   x        int       var       4      4
#   y        int       var       4      8
#   t1       int       temp      4     16
#   t2       int       temp      4     20
#   t3       int       temp      4     24
    debug := 0
    t1 := 2 * 3
    t2 := 10 + t1
    x := t2
    if debug == 1 goto L1
    goto L2
L1:
    print x
L2:
    t3 := x * 2
    y := t3
