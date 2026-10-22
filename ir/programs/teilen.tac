# frame main, depth 0, size 24
#   name     type      kind   size offset
#   n        int       var       4      0
#   d        int       var       4      4
#   q        int       var       4      8
#   t1       int       temp      4     16
    n := 10
    d := 0
    if d != 0 goto L4
    goto L2
L4:
    t1 := n / d
    if t1 > 2 goto L1
    goto L2
L1:
    q := 1
    goto L3
L2:
    q := 0
L3:
    print q
