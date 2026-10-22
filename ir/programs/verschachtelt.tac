# frame main, depth 0, size 16
#   name     type      kind   size offset
#   m        int       var       4      0
#   t1       int       temp      4      8
#   t2       int       temp      4     12
# frame max, depth 1, size 24
#   name     type      kind   size offset
#   a        int       param     4     16
#   b        int       param     4     20
    goto main
max:
    if a > b goto L1
    goto L2
L1:
    return a
    goto L3
L2:
    return b
L3:
    return
main:
    param 16
    param 9
    t1 := call max, 2
    param 3
    param t1
    t2 := call max, 2
    m := t2
