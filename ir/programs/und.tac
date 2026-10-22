# frame main, depth 0, size 24
#   name     type      kind   size offset
#   a        int       var       4      0
#   b        int       var       4      4
#   c        int       var       4      8
#   d        int       var       4     12
#   r        int       var       4     16
    a := 5
    b := 2
    c := 4
    d := 3
    if a < b goto L4
    goto L2
L4:
    if c < d goto L1
    goto L2
L1:
    r := 1
    goto L3
L2:
    r := 0
L3:
    print r
