# frame main, depth 0, size 40
#   name     type      kind   size offset
#   a        int       var       4      0
#   b        int       var       4      4
#   p        int       var       4      8
#   q        int       var       4     12
#   t1       int       temp      4     16
#   t2       int       temp      4     20
#   t3       int       temp      4     24
#   t4       int       temp      4     28
#   t5       int       temp      4     32
    a := 4
    b := 7
    if a < b goto L1
    goto L2
L1:
    t1 := a * b
    t2 := t1 - 1
    p := t2
    goto L3
L2:
    t3 := a * b
    t4 := t3 + 2
    q := t4
L3:
    t5 := a * b
    print t5
