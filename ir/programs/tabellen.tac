# frame main, depth 0, size 24
#   name     type      kind   size offset
#   n        int       var       4      0
#   r        float     var       4      4
#   s        float     var       4      8
#   t2       int       temp      4     16
# frame triple, depth 1, size 32
#   name     type      kind   size offset
#   a        int       param     4     16
#   s        int       var       4     20
#   t1       int       temp      4     24
    goto main
triple:
    t1 := a * n
    s := t1
    return s
main:
    n := 3
    param 5
    t2 := call triple, 1
    print t2
