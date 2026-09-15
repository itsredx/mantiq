# ── Mathematical Operations Engine ─────────────────────────────────────
def add(a: int, b: int) -> int:
    return a + b

def multiply(a: int, b: int) -> int:
    return a * b

def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a: int = 0
    b: int = 1
    i: int = 2
    while i <= n:
        temp: int = a + b
        a = b
        b = temp
        i = i + 1
    return b

def is_prime(n: int) -> bool:
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i: int = 5
    while (i * i) <= n:
        if (n % i == 0) or (n % (i + 2) == 0):
            return False
        i = i + 6
    return True
