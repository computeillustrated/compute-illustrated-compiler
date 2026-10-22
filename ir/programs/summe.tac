# frame main, depth 0, size 8
#   name     type      kind   size offset
#   t3       int       temp      4      0
# frame sum, depth 1, size 40
#   name     type      kind   size offset
#   n        int       param     4     16
#   i        int       var       4     20
#   s        int       var       4     24
#   t1       int       temp      4     32
#   t2       int       temp      4     36
    goto main
sum:
    i := 1
    s := 0
L1:
    if i <= n goto L2
    goto L3
L2:
    t1 := s + i
    s := t1
    t2 := i + 1
    i := t2
    goto L1
L3:
    return s
main:
    param 100
    t3 := call sum, 1
    print t3
