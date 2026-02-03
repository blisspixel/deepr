"""Setup for Deepr API Common library."""
from setuptools import setup, find_packages

setup(
    name='deepr-api-common',
    version='1.0.0',
    packages=find_packages(),
    python_requires='>=3.9',
    description='Common utilities for Deepr cloud API handlers',
    author='Deepr',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
