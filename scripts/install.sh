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
echo "Checking environment variables..."
missing=0
if [ -z "$OPENAI_API_KEY" ]; then
    echo "  ⚠ OPENAI_API_KEY not set (required for research)"
    missing=1
fi
for key in XAI_API_KEY GEMINI_API_KEY AZURE_OPENAI_API_KEY; do
    if [ -n "${!key}" ]; then
        echo "  ✓ $key set"
    fi
done
if [ $missing -eq 1 ]; then
    echo "  Set required keys in .env or your shell profile"
fi

echo
echo "Installation complete! You can now use 'deepr' from anywhere."
echo
echo "Quick start:"
echo "  deepr --help                   # Show all commands"
echo "  deepr doctor                   # Check configuration"
echo "  deepr expert list              # List experts"
echo "  deepr research \"query\"         # Run research"
echo
echo "MCP server:"
echo "  python -m deepr.mcp.server     # Start MCP server (stdio)"
echo
