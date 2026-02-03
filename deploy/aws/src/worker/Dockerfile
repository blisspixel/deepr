FROM python:3.11-slim

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install AWS CLI for secrets access
RUN pip install --no-cache-dir awscli boto3

# Copy and install deepr
COPY pyproject.toml setup.py README.md ./
COPY deepr/__init__.py deepr/__init__.py
RUN pip install --no-cache-dir .

# Copy application code
COPY deepr/ deepr/
COPY deploy/aws/src/worker/worker.py ./worker.py

# Switch to non-root user
USER deepr

# Worker entry point
CMD ["python", "worker.py"]
