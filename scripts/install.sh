#!/usr/bin/env bash
# Deepr installation script for Linux and macOS

set -e

echo "Installing Deepr..."
echo

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.9 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Found Python $PYTHON_VERSION"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "ERROR: pip3 is not installed"
    echo "Please install pip: python3 -m ensurepip --upgrade"
    exit 1
fi

echo
echo "Installing Deepr package..."
pip3 install -e .

echo
echo "Installation complete!"
echo
echo "Next steps:"
echo "  1. Copy .env.example to .env: cp .env.example .env"
echo "  2. Edit .env and add your OPENAI_API_KEY"
echo "  3. Run: deepr --version"
echo
echo "If 'deepr' command not found, add to PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
echo
