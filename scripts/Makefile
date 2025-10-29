.PHONY: help install install-dev test clean build publish

help:
	@echo "Deepr - Research automation platform"
	@echo ""
	@echo "Available commands:"
	@echo "  make install      - Install Deepr"
	@echo "  make install-dev  - Install with development dependencies"
	@echo "  make test         - Run tests"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make build        - Build distribution packages"
	@echo "  make publish      - Publish to PyPI (requires credentials)"
	@echo "  make run          - Run worker and API"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete

build: clean
	python -m build

publish: build
	python -m twine upload dist/*

run:
	@echo "Starting Deepr services..."
	@echo "Worker: python bin/start-worker.py"
	@echo "API: python -m deepr.api.app"
	@echo ""
	@echo "Run these in separate terminals or use a process manager"
