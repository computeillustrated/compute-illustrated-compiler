# frame main, depth 0, size 24
#   name     type      kind   size offset
#   i        int       var       4      0
#   s        int       var       4      4
#   t1       int       temp      4      8
#   t2       int       temp      4     12
#   t3       int       temp      4     16
    s := 0
    i := 0
L1:
    if i < 3 goto L2
    goto L3
L2:
    t1 := i * i
    t2 := s + t1
    s := t2
    t3 := i + 1
    i := t3
    goto L1
L3:
    print s
