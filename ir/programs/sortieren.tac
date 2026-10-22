# frame main, depth 0, size 152
#   name     type      kind   size offset
#   a        int[5]    var      24      0
#   i        int       var       4     24
#   j        int       var       4     28
#   n        int       var       4     32
#   h        int       var       4     36
#   t1       int       temp      4     40
#   t2       int       temp      4     44
#   t3       int       temp      4     48
#   t4       int       temp      4     52
#   t5       int       temp      4     56
#   t6       int       temp      4     60
#   t7       int       temp      4     64
#   t8       int       temp      4     68
#   t9       int       temp      4     72
#   t10      int       temp      4     76
#   t11      int       temp      4     80
#   t12      int       temp      4     84
#   t13      int       temp      4     88
#   t14      int       temp      4     92
#   t15      int       temp      4     96
#   t16      int       temp      4    100
#   t17      int       temp      4    104
#   t18      int       temp      4    108
#   t19      int       temp      4    112
#   t20      int       temp      4    116
#   t21      int       temp      4    120
#   t22      int       temp      4    124
#   t23      int       temp      4    128
#   t24      int       temp      4    132
#   t25      int       temp      4    136
#   t26      int       temp      4    140
#   t27      int       temp      4    144
    t1 := 4 * 0
    a[t1] := 7
    t2 := 4 * 1
    a[t2] := 3
    t3 := 4 * 2
    a[t3] := 9
    t4 := 4 * 3
    a[t4] := 1
    t5 := 4 * 4
    a[t5] := 5
    n := 5
    i := 0
L1:
    t6 := n - 1
    if i < t6 goto L2
    goto L3
L2:
    j := 0
L4:
    t7 := n - 1
    t8 := t7 - i
    if j < t8 goto L5
    goto L6
L5:
    t9 := 4 * j
    t10 := a[t9]
    t11 := j + 1
    t12 := 4 * t11
    t13 := a[t12]
    if t10 > t13 goto L7
    goto L8
L7:
    t14 := 4 * j
    t15 := a[t14]
    h := t15
    t16 := 4 * j
    t17 := j + 1
    t18 := 4 * t17
    t19 := a[t18]
    a[t16] := t19
    t20 := j + 1
    t21 := 4 * t20
    a[t21] := h
L8:
    t22 := j + 1
    j := t22
    goto L4
L6:
    t23 := i + 1
    i := t23
    goto L1
L3:
    t24 := 4 * 0
    t25 := a[t24]
    print t25
    t26 := 4 * 4
    t27 := a[t26]
    print t27
