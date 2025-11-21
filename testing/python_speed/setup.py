# setup.py
from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

extensions = [
    Extension(
        name="cy_speed",
        sources=["cy_speed.pyx"],
        include_dirs=[np.get_include()],
    )
]

setup(
    name="cy_speed",
    ext_modules=cythonize(
        extensions,
        language_level="3",
    ),
)
