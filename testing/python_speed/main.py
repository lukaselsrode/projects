import os
import timeit
import numpy as np
from numba import njit, types, cuda
from numba.typed import List
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import cy_speed


def measure(foo, *args, n=100, **kwargs):
    """
    For 'normal' functions (pure Python, Numba, Cython, NumPy, Torch).
    Warms up once, then measures average over n calls.
    """
    # Warm-up call (compile for Numba, load for Cython, etc.)
    foo(*args, **kwargs)

    def wrapper():
        return foo(*args, **kwargs)

    execution_time = timeit.timeit(wrapper, number=n)
    print(f"{foo.__name__}: {execution_time / n:.8f} [s per call] (n={n})")


def measure_once(foo, *args, **kwargs):
    """
    For multiprocessing / threading / CUDA/MPS where we don't want to
    spawn a whole pool or launch kernels n times inside timeit.
    """
    def wrapper():
        return foo(*args, **kwargs)

    execution_time = timeit.timeit(wrapper, number=1)
    print(f"{foo.__name__}: {execution_time:.8f} [s single run]")


# ------------------------- core scalar foo ------------------------- #

def foo(x: int):
    return (x + 12) // 7


# ------------------------- NumPy versions -------------------------- #

def numpy_expr(xs: np.ndarray) -> np.ndarray:
    """
    Proper NumPy vectorized expression.
    This is the "right" way to do it with NumPy.
    """
    return (xs + 12) // 7


# np.vectorize is a convenience wrapper, not real vectorization.
np_foo_vec = np.vectorize(foo)

def numpy_vectorize(xs: np.ndarray) -> np.ndarray:
    """
    np.vectorize wrapper around foo.
    Usually slower than numpy_expr, often slower than plain loops.
    """
    return np_foo_vec(xs)


# ---------------------- Python loop variants ----------------------- #

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


# ------------------------- Numba (CPU) ----------------------------- #

@njit
def numba_foo(x: int):
    return (x + 12) // 7


@njit
def numbar(xs):
    rv = List.empty_list(types.float64)
    for i in range(len(xs)):
        rv.append(numba_foo(xs[i]))
    return rv


@njit
def numbar_fast(xs):
    n = len(xs)
    out = np.empty(n, dtype=np.int64)
    for i in range(n):
        out[i] = numba_foo(xs[i])
    return out


# ---------------- threading / multiprocessing ---------------------- #

def threaded_map(xs, max_workers=(os.cpu_count() - 1)):
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(foo, xs))


def _mp_worker(x):
    return foo(x)


def multiproc_map(xs, max_workers=(os.cpu_count() - 1)):
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(_mp_worker, xs))


# ------------------------- CUDA (Numba) ---------------------------- #

@cuda.jit
def numba_foo_kernel(xs, out):
    """
    CUDA kernel: out[i] = (xs[i] + 12) // 7
    xs, out: 1D device arrays
    """
    i = cuda.grid(1)
    if i < xs.size:
        out[i] = (xs[i] + 12) // 7


def numbar_cuda(xs_np: np.ndarray) -> np.ndarray:
    """
    Host wrapper around the CUDA kernel.
    xs_np: 1D NumPy array (int64)
    returns: 1D NumPy array (int64)
    """
    n = xs_np.size

    # Move data to device
    d_xs = cuda.to_device(xs_np)
    d_out = cuda.device_array_like(xs_np)

    # Configure blocks & grid
    threads_per_block = 256
    blocks_per_grid = (n + threads_per_block - 1) // threads_per_block

    # Launch kernel
    numba_foo_kernel[blocks_per_grid, threads_per_block](d_xs, d_out)

    # Ensure completion before timing ends
    cuda.synchronize()

    # Copy back to host
    return d_out.copy_to_host()


# ------------------------- Torch MPS (Mac) ------------------------- #

def torch_mps_version(xs_np: np.ndarray) -> np.ndarray:
    """
    Run (x + 12) // 7 on Apple's Metal (MPS) backend via PyTorch.
    Falls back to CPU if MPS is not available.
    """
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Running Torch Using {device}")
    x = torch.from_numpy(xs_np).to(device)
    y = (x + 12) // 7
    return y.cpu().numpy()


# ----------------------------- main -------------------------------- #

if __name__ == "__main__":
    # Big enough to see differences, but still quick to run
    X = np.arange(1_000_000, dtype=np.int64)
    X_list = X.tolist()

    print("=== Python single-threaded ===")
    measure(for_loop, X_list.copy())
    measure(list_comp, X_list.copy())
    measure(while_loop, X_list.copy())
    measure(anon_func, X_list.copy())
    # recursive omitted here for size > ~1000

    print("\n=== NumPy ===")
    measure(numpy_expr, X, n=100)
    measure(numpy_vectorize, X, n=100)

    print("\n=== Numba (CPU) ===")
    measure(numbar, X, n=100)
    measure(numbar_fast, X, n=100)

    print("\n=== Cython ===")
    measure(cy_speed.cy_numbar, X, n=100)

    print("\n=== Multithreading / Multiprocessing (single big run) ===")
    measure_once(threaded_map, X_list.copy())
    measure_once(multiproc_map, X_list.copy())

    print("\n=== CUDA (Numba) ===")
    if cuda.is_available():
        # warmup
        numbar_cuda(X)
        measure_once(numbar_cuda, X)
    else:
        print("CUDA not available on this system, skipping numbar_cuda")

    print("\n=== Torch MPS (Apple GPU) ===")
    try:
        import torch
        if torch.backends.mps.is_available():
            # warmup
            torch_mps_version(X)
            measure_once(torch_mps_version, X)
        else:
            print("Torch MPS not available (no supported Apple GPU or backend).")
    except ImportError:
        print("PyTorch not installed, skipping Torch MPS benchmark.")
