# frame main, depth 0, size 32
#   name     type      kind   size offset
#   a        int       var       4      0
#   b        int       var       4      4
#   c        int       var       4      8
#   d        int       var       4     12
#   r        int       var       4     16
#   q        int       var       4     20
#   p        int       var       4     24
    a := 1
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
    if a < b goto L5
    goto L8
L8:
    if c < d goto L5
    goto L6
L5:
    q := 1
    goto L7
L6:
    q := 0
L7:
    print q
    if a < b goto L10
    goto L9
L9:
    p := 1
    goto L11
L10:
    p := 0
L11:
    print p
