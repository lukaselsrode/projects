#!/bin/bash
python3 setup.py build_ext --inplace
pythran pythran_bench.py -o pythran_bench.so
python3 benchmark_plot.py