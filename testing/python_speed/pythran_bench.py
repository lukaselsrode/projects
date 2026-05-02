# pythran export pythran_foo(int64[])
import numpy as np

def pythran_foo(x):
    return (x + 12) // 7