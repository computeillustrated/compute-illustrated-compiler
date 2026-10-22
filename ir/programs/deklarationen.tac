# frame main, depth 0, size 80
#   name     type      kind   size offset
#   n        int       var       4      0
#   r        float     var       4      4
#   s        float     var       4      8
#   v        int[5]    var      24     16
#   t1       int       temp      4     40
#   t2       float     temp      4     44
#   t3       float     temp      4     48
#   t4       float     temp      4     52
#   t5       int       temp      4     56
#   t6       int       temp      4     60
#   t7       int       temp      4     64
#   t8       int       temp      4     68
#   t9       int       temp      4     72
    n := 3
    t1 := n / 2
    t2 := inttofloat t1
    t3 := t2 + 0.5
    r := t3
    t4 := inttofloat n
    s := t4
    t5 := 4 * n
    t6 := n * 2
    v[t5] := t6
    t7 := 4 * n
    t8 := v[t7]
    t9 := t8 + 1
    print t9
