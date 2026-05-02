import numpy as np
import matplotlib.pyplot as plt
import timeit
import os
import sys
import gc
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from numba import cuda, njit, types
from numba.typed import List
import scipy.sparse as sp
import cy_speed
 
# Core function
def foo(x):
    if hasattr(x, '__len__') and not isinstance(x, (str, bytes)):
        return (x + 12) // 7
    return (int(x) + 12) // 7

# Python loop variants
def for_loop(xs):
    rv = []
    for x in xs:
        rv.append(foo(x))
    return rv

def list_comp(xs):
    return [foo(x) for x in xs]

def while_loop(xs):
    rv = []
    i = 0
    n = len(xs)
    while i < n:
        rv.append(foo(xs[i]))
        i += 1
    return rv

def recursive(xs, index=0):
    if index == len(xs):
        return []
    return [foo(xs[index])] + recursive(xs, index + 1)

def anon_func(xs):
    return list(map(lambda x: foo(x), xs))

# Numba implementations
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

# Threading/Multiprocessing
def _mp_worker(x):
    return foo(x)

def threaded_map(xs, max_workers=(os.cpu_count() - 1)):
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(foo, xs))

def multiproc_map(xs, max_workers=(os.cpu_count() - 1)):
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(_mp_worker, xs))

# CUDA Implementation
@cuda.jit
def numba_foo_kernel(xs, out):
    i = cuda.grid(1)
    if i < xs.size:
        out[i] = (xs[i] + 12) // 7

def numbar_cuda(xs_np: np.ndarray) -> np.ndarray:
    n = xs_np.size
    d_xs = cuda.to_device(xs_np)
    d_out = cuda.device_array_like(xs_np)
    threads_per_block = 256
    blocks_per_grid = (n + threads_per_block - 1) // threads_per_block
    numba_foo_kernel[blocks_per_grid, threads_per_block](d_xs, d_out)
    cuda.synchronize()
    return d_out.copy_to_host()

# Torch MPS Implementation
def torch_mps_version(xs_np: np.ndarray) -> np.ndarray:
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    x = torch.from_numpy(xs_np).to(device)
    y = (x + 12) // 7
    return y.cpu().numpy()

import warnings
import contextlib
import io

# Suppress warnings
warnings.filterwarnings('ignore', category=UserWarning, module='taichi')
os.environ['TI_VERBOSE_IMPORT'] = '0'
os.environ['TI_DEVICE_MEMORY_GB'] = '1'  # Limit GPU memory usage

# Suppress Taichi's welcome message
with contextlib.redirect_stdout(io.StringIO()):
    try:
        import taichi as ti
        ti.init(arch=ti.cpu, log_level=ti.ERROR)
    except ImportError:
        pass

# Import optimized implementations with clean output
OPTIMIZED_IMPORTS = True
optimized_imports = {}

try:
    from optimized_implementations import (
        numba_vectorized, numba_jit_foo, pythran_foo, 
        numexpr_foo, bottleneck_foo, ti_foo
    )
    optimized_imports.update({
        'numba_vectorized': numba_vectorized,
        'numba_jit_foo': numba_jit_foo,
        'pythran_foo': pythran_foo,
        'numexpr_foo': numexpr_foo,
        'bottleneck_foo': bottleneck_foo,
        'ti_foo': ti_foo
    })
    
    # Optional imports with silent failures
    try:
        from optimized_implementations import transonic_foo
        optimized_imports['transonic_foo'] = transonic_foo
    except (ImportError, Exception):
        pass
        
    try:
        from optimized_implementations import cupy_foo
        optimized_imports['cupy_foo'] = cupy_foo
    except (ImportError, Exception):
        pass
        
    try:
        from optimized_implementations import bohrium_foo
        optimized_imports['bohrium_foo'] = bohrium_foo
    except (ImportError, Exception):
        pass
        
except ImportError as e:
    OPTIMIZED_IMPORTS = False
    warnings.warn(f"Some optimized implementations are not available: {e}", ImportWarning)

# Cleanup function for CUDA
def cuda_cleanup():
    if cuda.is_available():
        cuda.current_context().reset()
    gc.collect()

def benchmark_sparse_dense(size, sparsity=0.01):
    """Benchmark sparse vs dense operations."""
    if size > 10000:  # Skip very large sizes to avoid memory issues
        return np.nan, np.nan
        
    try:
        # Dense array
        dense = np.random.randint(0, 100, size=size, dtype=np.int64)
        
        # Sparse matrix (CSR format)
        # Ensure we have at least one non-zero element
        sparse = sp.random(size, 1, density=max(1/size, sparsity), format='csr', dtype=np.int64)
        
        # Time dense operation
        def run_dense():
            result = np.empty_like(dense)
            for i in range(len(dense)):
                result[i] = (dense[i] + 12) // 7
            return result
        
        # Time sparse operation (only on non-zero elements)
        def run_sparse():
            result = np.empty_like(sparse.data)
            for i in range(len(sparse.data)):
                result[i] = (sparse.data[i] + 12) // 7
            return result
        
        dense_time = min(timeit.repeat(run_dense, number=1, repeat=3))
        sparse_time = min(timeit.repeat(run_sparse, number=1, repeat=3))
        
        return dense_time, sparse_time
    except Exception as e:
        print(f"Skipping sparse_dense with size {size}: {str(e)}")
        return np.nan, np.nan

def benchmark_memmap(size=100_000):
    """Benchmark memory-mapped arrays vs in-memory arrays."""
    if size < 10:  # Skip very small sizes
        return np.nan, np.nan
        
    filename = 'temp_memmap.npy'
    
    try:
        # Create memory-mapped array
        mmap_arr = np.memmap(filename, dtype='int64', mode='w+', shape=(size,))
        mmap_arr[:] = np.random.randint(0, 100, size=size)
        mmap_arr.flush()  # Write to disk
        
        # Create in-memory array
        mem_arr = np.random.randint(0, 100, size=size, dtype=np.int64)
        
        # Time memory-mapped
        def run_mmap():
            result = np.empty_like(mmap_arr)
            for i in range(len(mmap_arr)):
                result[i] = (mmap_arr[i] + 12) // 7
            return result
            
        # Time in-memory
        def run_mem():
            result = np.empty_like(mem_arr)
            for i in range(len(mem_arr)):
                result[i] = (mem_arr[i] + 12) // 7
            return result
            
        mmap_time = min(timeit.repeat(run_mmap, number=1, repeat=3))
        mem_time = min(timeit.repeat(run_mem, number=1, repeat=3))
        
        return mmap_time, mem_time
    finally:
        # Clean up
        if 'mmap_arr' in locals():
            del mmap_arr
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass

def setup_benchmark_env():
    # Import torch only if available
    try:
        import torch
        TORCH_AVAILABLE = torch.backends.mps.is_available()
    except ImportError:
        TORCH_AVAILABLE = False
    
    # Check CUDA availability
    CUDA_AVAILABLE = cuda.is_available()
    
    # Define all implementations to test
    implementations = {
        # Basic Python implementations
        'For Loop': for_loop,
        'List Comp': list_comp,
        'While Loop': lambda x: while_loop(x.copy()),
        'Map + Lambda': anon_func,
        'Recursive': lambda x: recursive(x.copy() if hasattr(x, 'copy') else list(x)),
        
        # Vectorized/optimized implementations
        'NumPy Vectorized': numpy_expr,
        'NumPy Vectorize': numpy_vectorize,
        'Numba JIT': numbar_fast,
        'Numba @vectorize (parallel)': lambda x: numba_vectorized(x).tolist(),
        'Numba @jit (parallel)': numba_jit_foo,
        'Cython': cy_speed.cy_numbar,
        
        # Parallel implementations
        'ThreadPool': lambda x: list(ThreadPoolExecutor(max_workers=os.cpu_count()-1).map(foo, x)),
        'ProcessPool': lambda x: list(ProcessPoolExecutor(max_workers=os.cpu_count()-1).map(_mp_worker, x)),
    }
    
    # Add optimized implementations if available
    if OPTIMIZED_IMPORTS:
        optimized_impls = {
            'Transonic': transonic_foo,
            'NumExpr': numexpr_foo,
            'Bottleneck': bottleneck_foo,
            'Taichi': ti_foo,
        }
        
        if CUDA_AVAILABLE:
            optimized_impls['CuPy'] = cupy_foo
            
        if 'bohrium_foo' in optimized_imports:
            optimized_impls['Bohrium'] = bohrium_foo
            
        implementations.update(optimized_impls)
    
    # Add GPU implementations
    if CUDA_AVAILABLE:
        implementations['CUDA'] = numbar_cuda
    
    if TORCH_AVAILABLE:
        implementations['PyTorch MPS'] = torch_mps_version
    
    # Add special benchmarks
    implementations.update({
        'Sparse vs Dense': benchmark_sparse_dense,
        'Memory Mapped': benchmark_memmap
    })
    
    return implementations

def benchmark_implementation(func, input_sizes, num_runs=5):
    """Benchmark a single implementation across different input sizes."""
    times = []
    for size in input_sizes:
        try:
            # Create input data
            x = np.random.randint(0, 100, size=size, dtype=np.int64)
            
            # Special handling for while_loop and recursive which modify their input
            if func.__name__ in ['while_loop', 'recursive']:
                x_list = x.tolist()
                def run():
                    return func(x_list.copy() if func.__name__ == 'while_loop' else x_list)
            else:
                def run():
                    return func(x)
            
            # Time the function
            timer = timeit.Timer(run)
            times.append(min(timer.repeat(repeat=num_runs, number=1)) / 1)
            
        except Exception as e:
            print(f"Error running {func.__name__} with size {size}: {e}")
            times.append(np.nan)
            
    return times

def plot_results(input_sizes, results):
    """Plot the benchmark results with improved visualization."""
    plt.figure(figsize=(16, 12))
    
    # Main performance plot
    ax1 = plt.subplot(2, 1, 1)
    
    # Sort implementations by performance (fastest first, on average)
    def get_avg_time(times):
        if isinstance(times, dict) or not len(times):
            return float('inf')
        return np.nanmean([t for t in times if t > 0] or [float('inf')])
    
    sorted_impls = sorted(
        [(name, times) for name, times in results.items() if not isinstance(times, dict)],
        key=lambda x: get_avg_time(x[1])
    )
    
    # Plot each implementation
    for name, times in sorted_impls:
        if len(times) == len(input_sizes):
            valid_indices = [i for i, t in enumerate(times) if t is not None and not np.isnan(t) and t > 0]
            if valid_indices:
                x = [input_sizes[i] for i in valid_indices]
                y = [times[i] for i in valid_indices]
                line, = ax1.plot(x, y, 'o-', markersize=4, label=name)
    
    ax1.set_xscale('log')
    ax1.set_yscale('log')
    ax1.set_xlabel('Input Size (log scale)', fontsize=12)
    ax1.set_ylabel('Execution Time (seconds, log scale)', fontsize=12)
    ax1.set_title('Performance Comparison of Different Implementations', fontsize=14, pad=20)
    
    # Add grid and legend
    ax1.grid(True, which="both", ls="-", alpha=0.2)
    ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    
    # Add special benchmarks as text
    ax2 = plt.subplot(2, 1, 2)
    ax2.axis('off')
    
    text_content = ["\nBenchmark Results:", "-" * 30]
    
    # Add timing results for special benchmarks
    for name, times in results.items():
        if isinstance(times, dict):
            if 'dense' in times:  # Sparse vs Dense results
                text_content.append("\nSparse (1%) vs Dense Arrays (size=1,000,000):")
                text_content.append(f"  {'Dense:':<15} {times['dense']:.6f} s")
                text_content.append(f"  {'Sparse:':<15} {times['sparse']:.6f} s")
                text_content.append(f"  Sparse is {times['dense']/max(times['sparse'], 1e-9):.1f}x faster")
                
            elif 'memory_mapped' in times:  # Memory-mapped results
                text_content.append("\nMemory-Mapped vs In-Memory Arrays (size=10,000,000):")
                text_content.append(f"  {'In-Memory:':<15} {times['in_memory']:.6f} s")
                text_content.append(f"  {'Memory-Mapped:':<15} {times['memory_mapped']:.6f} s")
                text_content.append(f"  Overhead: {times['memory_mapped']/max(times['in_memory'], 1e-9):.1f}x")
    
    # Add system info
    import platform
    text_content.extend([
        "\nSystem Info:",
        "-" * 30,
        f"Python: {platform.python_version()}",
        f"NumPy: {np.__version__}",
        f"Numba: {np.__version__}",
        f"OS: {platform.system()} {platform.release()}",
        f"Processor: {platform.processor()}",
        f"Cores: {os.cpu_count()}"
    ])
    
    ax2.text(0.1, 0.5, "\n".join(text_content), 
            fontfamily='monospace', 
            va='top', 
            fontsize=10,
            bbox=dict(boxstyle='round', facecolor='whitesmoke', alpha=0.5))
    
    plt.tight_layout(rect=[0, 0, 0.75, 1])
    
    # Save high-resolution figure
    plt.savefig('performance_comparison.png', dpi=300, bbox_inches='tight')
    print("\nBenchmark results saved to 'performance_comparison.png'")
    
    # Also save as SVG for better quality in documents
    plt.savefig('performance_comparison.svg', bbox_inches='tight')
    
    plt.show()

def print_header():
    """Print a clean header with system information."""
    import platform
    import numpy as np
    
    print("\n" + "="*80)
    print(f"{'Python Benchmark Suite':^80}")
    print("="*80)
    print(f"Python: {platform.python_version()}")
    print(f"NumPy: {np.__version__}")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Processor: {platform.processor()}")
    print(f"Cores: {os.cpu_count()}")
    print("-"*80)
    print("Starting benchmarks...\n")

def main():
    # Print system information
    print_header()
    
    # Define input sizes to test (logarithmically spaced, max 100k for initial testing)
    input_sizes = np.logspace(0, 5, num=10, dtype=int)  # 10^0 to 10^5 (1 to 100,000)
    input_sizes = np.unique(input_sizes)  # Remove duplicates
    input_sizes = input_sizes[input_sizes <= 100_000]  # Ensure max is 100k
    
    # Setup environment and get implementations
    implementations = setup_benchmark_env()
    
    # Add special benchmarks
    implementations['Sparse vs Dense'] = benchmark_sparse_dense
    implementations['Memory Mapped'] = benchmark_memmap
    
    # Run benchmarks
    results = {}
    from tqdm import tqdm
    
    # Create a progress bar for all implementations
    with tqdm(implementations.items(), desc="Running benchmarks", unit="test") as pbar:
        for name, func in pbar:
            pbar.set_postfix_str(f"{name[:15]}...")
            try:
                times = benchmark_implementation(func, input_sizes)
                results[name] = times
            except Exception as e:
                tqdm.write(f"⚠️  Skipping {name}: {str(e).split('(')[0]}")
                continue

    # Plot results
    plot_results(input_sizes, results)

def numpy_expr(xs: np.ndarray) -> np.ndarray:
    """NumPy vectorized expression."""
    return (xs + 12) // 7

def numpy_vectorize(xs: np.ndarray) -> np.ndarray:
    """np.vectorize wrapper around foo."""
    return np.vectorize(foo)(xs)

if __name__ == "__main__":
    # Set up proper error handling
    try:
        # Run the benchmarks
        main()
    except KeyboardInterrupt:
        print("\nBenchmarking interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn error occurred during benchmarking: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup code if needed
        if cuda.is_available():
            cuda_cleanup()
        if 'cuda' in globals() and cuda.is_available():
            cuda_cleanup()

        # Clean up any temporary files
        if os.path.exists('temp_memmap.npy'):
            try:
                os.remove('temp_memmap.npy')
            except:
                pass