#!/bin/bash
# Install deepr CLI globally so it can be used anywhere

set -e  # Exit on error

echo "Installing deepr CLI..."
echo

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' || python --version 2>&1 | grep -oP '\d+\.\d+')
echo "Python version: $python_version"

# Install in editable mode for development
echo "Installing in editable mode..."
pip install -e .

# Verify installation
echo
echo "Verifying installation..."
if command -v deepr &> /dev/null; then
    echo "✓ deepr command is available"
    deepr --version || echo "deepr CLI installed successfully"
else
    echo "✗ deepr command not found in PATH"
    echo "  Try: pip install --user -e ."
    echo "  And ensure ~/.local/bin (or equivalent) is in your PATH"
    exit 1
fi

echo
echo "Installation complete! You can now use 'deepr' from anywhere."
echo
echo "Quick start:"
echo "  deepr --help                   # Show all commands"
echo "  deepr expert list              # List experts"
echo "  deepr expert chat <name>       # Chat with an expert"
echo "  deepr run focus <query>        # Run quick research"
echo
