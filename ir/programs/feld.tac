# frame main, depth 0, size 56
#   name     type      kind   size offset
#   a        int[4]    var      16      0
#   i        int       var       4     16
#   s        int       var       4     20
#   t1       int       temp      4     24
#   t2       int       temp      4     28
#   t3       int       temp      4     32
#   t4       int       temp      4     36
#   t5       int       temp      4     40
#   t6       int       temp      4     44
#   t7       int       temp      4     48
#   t8       int       temp      4     52
    i := 0
L1:
    if i < 4 goto L2
    goto L3
L2:
    t1 := 4 * i
    t2 := i * i
    a[t1] := t2
    t3 := i + 1
    i := t3
    goto L1
L3:
    t4 := 4 * 1
    t5 := a[t4]
    t6 := 4 * 3
    t7 := a[t6]
    t8 := t5 + t7
    s := t8
