# Installation Guide

Complete installation guide for Deepr on Linux, macOS, and Windows.

## Quick Install (5 minutes)

### Step 1: Install Deepr

**Linux / macOS:**
```bash
# Clone repository
git clone https://github.com/yourusername/deepr.git
cd deepr

# Install (this creates the 'deepr' command)
pip install -e .

# Verify installation
deepr --version
```

**Windows:**
```powershell
# Clone repository
git clone https://github.com/yourusername/deepr.git
cd deepr

# Install (this creates the 'deepr' command)
pip install -e .

# Verify installation
deepr --version
```

The `pip install -e .` command installs Deepr and creates the `deepr` command that works system-wide in your terminal.

### Step 2: Configure API Keys

```bash
# Copy example configuration
cp .env.example .env

# Edit configuration file
# Linux/macOS: nano .env
# Windows: notepad .env
# Or use any text editor
```

Add your API keys to `.env`:

```bash
# At minimum, add one provider key:

# OpenAI (recommended - includes Deep Research API)
OPENAI_API_KEY=sk-...

# OR Google Gemini (fast, cost-effective)
GEMINI_API_KEY=...

# OR xAI Grok (agentic search)
XAI_API_KEY=xai-...

# Optional: Azure OpenAI (enterprise)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...

# Optional: Budget limits
DEEPR_MAX_COST_PER_MONTH=50.0
```

**Getting API Keys:**
- OpenAI: https://platform.openai.com/api-keys
- Google Gemini: https://aistudio.google.com/app/apikey
- xAI Grok: https://console.x.ai/
- Azure OpenAI: https://portal.azure.com/

### Step 3: Set Your Budget

```bash
# Set monthly budget (one-time setup)
deepr budget set 50

# This protects you from unexpected costs
# Jobs auto-execute if under budget
# You'll be prompted when approaching limit
```

### Step 4: Run Your First Research

```bash
# Simple test query
deepr run single "What is 2+2?"

# Real research query
deepr run single "What are the latest developments in quantum computing as of 2025?"

# With specific provider
deepr run single "Explain transformer architecture" --provider gemini -m gemini-2.5-flash
```

That's it! You're ready to use Deepr.

## Advanced Installation

### From PyPI (when published)

```bash
pip install deepr
deepr --version
```

### Development Installation

For contributing to Deepr:

```bash
# Clone repository
git clone https://github.com/yourusername/deepr.git
cd deepr

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install in editable mode
pip install -e .

# Run tests
pytest
```

### Docker Installation (Optional)

```bash
# Build image
docker build -t deepr .

# Run with environment variables
docker run -e OPENAI_API_KEY=sk-... deepr run single "Your query"
```

## Configuration Details

### Environment Variables

Edit `.env` file:

```bash
# Provider API Keys
OPENAI_API_KEY=sk-...              # OpenAI (required for o3/o4-mini)
GEMINI_API_KEY=...                  # Google Gemini (optional)
XAI_API_KEY=xai-...                 # xAI Grok (optional)
AZURE_OPENAI_API_KEY=...            # Azure OpenAI (optional)
AZURE_OPENAI_ENDPOINT=...           # Azure endpoint (optional)
ANTHROPIC_API_KEY=...               # Anthropic (for planning, optional)

# Cost Controls
DEEPR_MAX_COST_PER_JOB=10.0         # Max cost per research job
DEEPR_MAX_COST_PER_DAY=100.0        # Daily spending limit
DEEPR_MAX_COST_PER_MONTH=1000.0     # Monthly spending limit

# Features
DEEPR_AUTO_REFINE=false             # Auto-optimize prompts (GPT-5-mini)

# Storage
DEEPR_RESULTS_DIR=data/reports      # Where reports are saved
DEEPR_QUEUE_DB=queue/research_queue.db  # Job queue database
```

### Recommended Provider Setup

**For most users:**
- Start with OpenAI (o4-mini-deep-research, ~$0.10 per query)
- Add Gemini for cost optimization (gemini-2.5-flash, ~$0.02 per query)

**For cost-conscious users:**
- Start with Gemini (excellent quality, very affordable)
- Add OpenAI for complex strategic analysis when needed

**For enterprise:**
- Use Azure OpenAI for compliance and governance
- Set strict budget limits in .env

## Troubleshooting

### Command Not Found: deepr

If `deepr --version` doesn't work after installation:

```bash
# Make sure pip installed to the right place
pip show deepr

# If installed but command not found, try:
python -m deepr.cli.main --version

# Or reinstall with:
pip uninstall deepr
pip install -e .
```

### Import Errors

```bash
# Missing dependencies
pip install -r requirements.txt

# Or reinstall
pip install -e .
```

### API Key Not Found

```bash
# Verify .env file exists
ls -la .env  # Linux/macOS
dir .env     # Windows

# Check if .env is in the correct directory (deepr project root)
# Not in ~/.env or elsewhere

# Verify key format (no quotes needed)
# Correct:   OPENAI_API_KEY=sk-abc123
# Incorrect: OPENAI_API_KEY="sk-abc123"
```

### Permission Errors (Linux/macOS)

```bash
# If pip install fails with permissions
pip install --user -e .

# Or use virtual environment (recommended)
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Verify Installation

```bash
# Check version
deepr --version

# Test help system
deepr --help
deepr run --help

# Test basic functionality (with API key configured)
deepr run single "What is 2+2?" -y

# Check budget status
deepr budget status

# List jobs
deepr list
```

## Platform-Specific Notes

### Linux
- Works on all major distributions (Ubuntu, Debian, Fedora, Arch)
- Python 3.9+ required
- May need `python3-dev` for some dependencies

### macOS
- Works on Intel and Apple Silicon
- Python 3.9+ required
- Install via Homebrew: `brew install python3`

### Windows
- Works on Windows 10/11
- Python 3.9+ required from python.org
- PowerShell or Command Prompt both supported
- Git Bash works but use native Python (not MinGW)

## Next Steps

After installation:

1. Read [Quick Start](../README.md#quick-start) for basic usage
2. Explore [CLI Commands](../README.md#cli-commands) for all features
3. Review [Best Practices](../README.md#best-practices-for-research-prompts) for effective prompts
4. Check [ROADMAP.md](ROADMAP.md) for upcoming features

## Getting Help

- Documentation: All markdown files in `docs/`
- Issues: https://github.com/yourusername/deepr/issues
- Questions: Create a GitHub discussion

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
