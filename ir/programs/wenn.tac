# frame main, depth 0, size 24
#   name     type      kind   size offset
#   x        int       var       4      0
#   y        int       var       4      4
#   t1       int       temp      4      8
#   t2       int       temp      4     12
#   t3       int       temp      4     16
#   t4       int       temp      4     20
    t1 := 2 * 3
    t2 := 10 + t1
    x := t2
    if x > 10 goto L1
    goto L2
L1:
    t3 := x - 10
    y := t3
    goto L3
L2:
    t4 := 10 - x
    y := t4
L3:
    print y
