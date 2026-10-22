# Nested functions: order and shipping live inside main, add lives inside order.
# add reads n from order (one level out; it hides main's n) and price from main.

def main():
    price = 10
    n = 1

    def order(n):
        def add(k):
            if k == n:
                return shipping() * n
            return price + add(k + 1)
        return add(0)

    def shipping():
        return price // 5

    print(order(n + 1))


main()
