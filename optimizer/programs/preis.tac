# frame main, depth 0, size 8
#   name     type      kind   size offset
#   t4       int       temp      4      0
#   t5       int       temp      4      4
# frame price, depth 1, size 40
#   name     type      kind   size offset
#   n        int       param     4     16
#   c        int       param     4     20
#   t1       int       temp      4     24
#   t2       int       temp      4     28
#   t3       int       temp      4     32
    goto main
price:
    if n > 10 goto L1
    goto L2
L1:
    t1 := n * c
    t2 := t1 - 5
    return t2
L2:
    t3 := n * c
    return t3
main:
    param 12
    param 3
    t4 := call price, 2
    print t4
    param 4
    param 3
    t5 := call price, 2
    print t5
