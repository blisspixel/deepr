from setuptools import setup, find_packages

setup(
    name="deepr",
    version="2.3.0",
    packages=find_packages(),
    install_requires=[
        "openai>=1.0.0",
        "flask>=3.0.0",
        "flask-cors>=4.0.0",
        "flask-socketio>=5.3.0",
        "python-socketio>=5.10.0",
        "python-dotenv>=1.0.0",
        "click>=8.1.0",
        "pydantic>=2.0.0",
        "aiofiles>=23.0.0",
        "python-docx>=0.8.11",
        "azure-identity>=1.12.0",
        "azure-servicebus>=7.11.0",
        "azure-storage-blob>=12.19.0",
    ],
    entry_points={
        "console_scripts": [
            "deepr=deepr.cli.main:main",
        ]
    },
    author="Nick Seal",
    author_email="nick@pueo.io",
    description="Research automation platform that replicates human research team workflows using AI.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
