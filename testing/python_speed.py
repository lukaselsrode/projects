import timeit
import numpy as np
from numba import njit, prange
from numba.typed import List

def measure(foo, *args, **kwargs):
    def wrapper():
        return foo(*args, **kwargs)
    execution_time = timeit.timeit(wrapper, number=1)
    print(f"{foo.__name__}: {execution_time}[s]")


def foo(x: int):
    return (x + 12) // 7

@njit  # Numba-compatible version of foo
def numba_foo(x: int):
    return (x + 12) // 7

def for_loop(xs):
    rv = []
    for x in xs:
        rv.append(foo(x))
    return rv


def list_comp(xs):
    return [foo(x) for x in xs]


def while_loop(xs):
    rv = []
    while xs:
        rv.append(foo(xs.pop(0)))
    return rv


def anon_func(xs):
    return list(map(lambda x: foo(x), xs))


def recursive(xs, index=0):
    if index == len(xs):
        return []
    return [foo(xs[index])] + recursive(xs, index + 1)


@njit(parallel=True)
def numbar(xs):
    rv = List()
    # Loop over the range in parallel
    for i in prange(len(xs)):
        rv.append(numba_foo(xs[i]))  # Use the Numba-compatible foo
    return rv

if __name__ == "__main__":
    X = np.arange(100)
    measure(for_loop, X.tolist())
    measure(list_comp, X.tolist())
    measure(while_loop, X.tolist())
    measure(anon_func, X.tolist())
    measure(recursive, X.tolist())
    numbar(X)
