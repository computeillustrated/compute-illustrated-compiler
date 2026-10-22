# frame main, depth 0, size 32
#   name     type      kind   size offset
#   x        int       var       4      0
#   y        int       var       4      4
#   t1       int       temp      4      8
#   t2       int       temp      4     12
#   t3       int       temp      4     16
#   t4       int       temp      4     20
#   t5       int       temp      4     24
#   t6       int       temp      4     28
    t1 := 2 * 3
    t2 := 10 + t1
    x := t2
    t3 := x * 2
    t4 := x * 2
    t5 := t4 * 3
    t6 := t3 + t5
    y := t6
