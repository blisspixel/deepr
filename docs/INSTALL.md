# Installation Guide

This guide covers installing Deepr on Linux, macOS, and Windows.

## Quick Install

### Linux / macOS

```bash
# Clone repository
git clone https://github.com/yourusername/deepr.git
cd deepr

# Install in development mode (editable)
pip install -e .

# Or install normally
pip install .

# Verify installation
deepr --version
```

### Windows

```powershell
# Clone repository
git clone https://github.com/yourusername/deepr.git
cd deepr

# Install in development mode (editable)
pip install -e .

# Or install normally
pip install .

# Verify installation
deepr --version
```

## From PyPI (when published)

```bash
pip install deepr
```

## Development Installation

For contributing to Deepr:

```bash
# Clone repository
git clone https://github.com/yourusername/deepr.git
cd deepr

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Configuration

After installation, set up your configuration:

```bash
# Copy example config
cp .env.example .env

# Edit with your API keys
# Linux/macOS:
nano .env
# Windows:
notepad .env
```

Required configuration:
- `OPENAI_API_KEY` - Your OpenAI API key

See [.env.example](.env.example) for all available options.

## Verify Installation

```bash
# Check version
deepr --version

# Test basic command
deepr research submit "What are the latest trends in AI?" --dry-run

# Check help
deepr --help
deepr research --help
```

## Platform-Specific Notes

### Linux

- Python 3.9+ required
- Works on Ubuntu 20.04+, Debian 11+, Fedora 35+, and most modern distributions
- May need to install python3-dev: `sudo apt install python3-dev`

### macOS

- Python 3.9+ required
- Works on macOS 11 (Big Sur) and later
- Install via Homebrew: `brew install python@3.11`

### Windows

- Python 3.9+ required
- Windows 10/11 supported
- Use PowerShell or Windows Terminal
- May need to enable long paths: `git config --system core.longpaths true`

## Docker Installation (Alternative)

```bash
# Build image
docker build -t deepr:latest .

# Run with environment file
docker run --env-file .env deepr:latest deepr research submit "Your prompt"

# Or run interactively
docker run -it --env-file .env deepr:latest bash
```

## Troubleshooting

### Command not found: deepr

After installation, if `deepr` command is not found:

**Linux/macOS:**
```bash
# Add to PATH
export PATH="$HOME/.local/bin:$PATH"
# Add to ~/.bashrc or ~/.zshrc to make permanent
```

**Windows:**
```powershell
# Pip install location
python -m site --user-site
# Add Scripts directory to PATH via System Properties > Environment Variables
```

### Import errors

```bash
# Reinstall dependencies
pip install --upgrade -e .
```

### Permission errors on Linux/macOS

```bash
# Use --user flag
pip install --user -e .
```

## Uninstall

```bash
pip uninstall deepr
```

## Next Steps

After installation:

1. Configure your API keys in `.env`
2. Read the [Quick Start](README.md#quick-start) guide
3. Try your first research job: `deepr research submit "Your question" --yes`
4. Explore commands: `deepr --help`

For more information, see [README.md](README.md) and [ROADMAP.md](ROADMAP.md).
