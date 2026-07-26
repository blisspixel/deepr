"""Setup for Deepr API Common library."""

from setuptools import find_packages, setup

setup(
    name="deepr-api-common",
    version="1.0.0",
    packages=find_packages(),
    python_requires=">=3.11",
    description="Common utilities for Deepr cloud API handlers",
    author="Deepr",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ],
)
