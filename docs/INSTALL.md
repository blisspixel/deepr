# Installation Guide

Complete installation guide for Deepr on Linux, macOS, and Windows.

## Quick Install (5 minutes)

### Step 1: Install Deepr

**Linux / macOS:**
```bash
# Clone repository
git clone https://github.com/blisspixel/deepr.git
cd deepr

# Install (this creates the 'deepr' command)
pip install -e .

# Verify installation
deepr --version
```

**Windows:**
```powershell
# Clone repository
git clone https://github.com/blisspixel/deepr.git
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

Add at least one API key to `.env`:

```bash
# Pick ANY one to start — Deepr works with a single provider.
# Add more keys later and auto mode will route to the best model per task.

OPENAI_API_KEY=sk-...      # Deep research + GPT-5/4.1 models
GEMINI_API_KEY=...          # Cost-effective, 1M+ context, Deep Research Agent
XAI_API_KEY=xai-...         # Cheapest ($0.01/query), real-time web search
ANTHROPIC_API_KEY=...       # Complex reasoning, coding (Extended Thinking)

# Enterprise options (optional):
# AZURE_OPENAI_KEY=...
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
# AZURE_PROJECT_ENDPOINT=...  # Azure AI Foundry (deep research + Bing)

# Budget limits (recommended):
DEEPR_MAX_COST_PER_MONTH=50.0
```

**Getting API Keys:**
- OpenAI: https://platform.openai.com/api-keys
- Google Gemini: https://aistudio.google.com/app/apikey
- xAI Grok: https://console.x.ai/
- Anthropic: https://console.anthropic.com/settings/keys
- Azure: https://portal.azure.com/

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
deepr research "What is 2+2?" --auto

# Real research query
deepr research "What are the latest developments in quantum computing?"

# With specific provider
deepr research "Explain transformer architecture" --provider gemini -m gemini-2.5-flash
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
git clone https://github.com/blisspixel/deepr.git
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
docker run -e OPENAI_API_KEY=sk-... deepr research "Your query" --auto
```

## Configuration Details

### Environment Variables

Edit `.env` file:

```bash
# Provider API Keys (at least one required — all optional individually)
OPENAI_API_KEY=sk-...              # OpenAI (deep research + GPT models)
GEMINI_API_KEY=...                  # Google Gemini (cost-effective, large context)
XAI_API_KEY=xai-...                 # xAI Grok (cheapest, real-time web search)
ANTHROPIC_API_KEY=...               # Anthropic (complex reasoning, coding)
# AZURE_OPENAI_KEY=...              # Azure OpenAI (enterprise)
# AZURE_OPENAI_ENDPOINT=...         # Azure endpoint
# AZURE_PROJECT_ENDPOINT=...        # Azure AI Foundry (enterprise deep research)

# Cost Controls
DEEPR_MAX_COST_PER_JOB=10.0         # Max cost per research job
DEEPR_MAX_COST_PER_DAY=100.0        # Daily spending limit
DEEPR_MAX_COST_PER_MONTH=1000.0     # Monthly spending limit

# Features
DEEPR_AUTO_REFINE=false             # Auto-optimize prompts before submission

# Storage
DEEPR_RESULTS_DIR=data/reports      # Where reports are saved
DEEPR_QUEUE_DB=queue/research_queue.db  # Job queue database
```

### Recommended Provider Setup

**Minimum (one key):** Any single provider works. Pick based on your priority:
- **OpenAI** — Best for deep research (o3/o4-mini)
- **Gemini** — Best value (excellent quality at low cost)
- **Grok** — Cheapest ($0.01/query), great for web search and news
- **Anthropic** — Best for complex reasoning and coding

**Recommended (two keys):** OpenAI + Grok or Gemini + Grok. This gives you deep research *and* a cheap fallback for simple queries. Auto mode routes appropriately.

**Full setup (all keys):** Auto mode has maximum flexibility — $0.01 for lookups, $0.04 for moderate queries, $0.50 for deep research. Each provider's strengths are used where they matter most.

**For enterprise:**
- Use Azure OpenAI or Azure AI Foundry for compliance and governance
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
deepr research --help

# Test basic functionality (with API key configured)
deepr research "What is 2+2?" --auto

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

## Uninstall

```bash
pip uninstall deepr
```

## Getting Help

- Documentation: All markdown files in `docs/`
- Issues: https://github.com/blisspixel/deepr/issues
- Questions: Create a GitHub discussion
