# cy_speed.pyx
# cython: boundscheck=False, wraparound=False, nonecheck=False, initializedcheck=False

import numpy as np
cimport numpy as np
from libc.stdint cimport int64_t


cdef inline int64_t cy_foo(int64_t x) nogil:
    return (x + 12) // 7

# Public function callable from Python
def cy_numbar(np.ndarray[np.int64_t, ndim=1] xs):
    """
    xs: 1D NumPy array of int64
    returns: 1D NumPy array of int64 with (x + 12) // 7 applied elementwise
    """
    cdef Py_ssize_t n = xs.shape[0]
    cdef np.ndarray[np.int64_t, ndim=1] out = np.empty(n, dtype=np.int64)
    cdef Py_ssize_t i

    # Tight C-level loop
    for i in range(n):
        out[i] = cy_foo(xs[i])

    return out
