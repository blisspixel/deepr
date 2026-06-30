# Installation Guide

Complete installation guide for Deepr on Linux, macOS, and Windows.

## Quick Install (5 minutes)

**Deepr works on Windows, macOS, and Linux** (Python 3.12+). The package on PyPI is `deepr-research`; the CLI command is `deepr`.

### Recommended: virtual environment (avoids Windows PATH surprises)

**Linux / macOS:**
```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr

python -m venv .venv
source .venv/bin/activate

pip install -e .          # core
# pip install -e ".[full]"  # web + everything

cp .env.example .env
deepr doctor && deepr budget set 50
deepr --version
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/blisspixel/deepr.git
cd deepr

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e .          # core
# pip install -e ".[full]"  # web + everything

cp .env.example .env
deepr doctor && deepr budget set 50
deepr --version
```

**Alternative with pipx** (simplest for CLI tools - handles isolation + PATH automatically):

```bash
pipx install -e .
# later from PyPI: pipx install deepr-research
```

### Bare / fast path (works if you previously fixed the user PATH)

```powershell
pip install -e .
```

**Windows note:** Bare installs with a global Python often put the CLI in `%APPDATA%\Python\Python312\Scripts`, which may not be on PATH. The venv/pipx recommendations above are strongly preferred. recon-tool (for native domain intel in experts) is **optional** - `deepr doctor` will suggest it when useful, but it is not a required dependency.


```powershell
pip install -e .
```

**Windows note (common gotcha):** A bare `pip install` with a global Python (e.g. `C:\Program Files\Python...`) without admin rights puts scripts in your user `%APPDATA%\Python\Python312\Scripts`. That folder is often missing from `PATH`, so `deepr` won't be found even though the package installed. The venv or pipx path above is the reliable fix. (We now document this pattern across projects.)

**Note on optional recon-tool:** `deepr doctor` may suggest `pip install -U recon-tool` for enhanced native domain intelligence in experts. This is **optional** - not a hard dependency. It adds passive DNS recon when available.

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
# Pick ANY one to start - Deepr works with a single provider.
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

**Optional enhancement:** `deepr doctor` may suggest `pip install -U recon-tool` for native passive DNS recon in experts. This is **not a hard dependency** - it only unlocks extra signals when present.

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

### From PyPI

```bash
pip install deepr-research
deepr --version
```

### Development Installation (recommended)

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr

# Create + activate venv (strongly recommended)
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate

pip install -e ".[dev,full]"   # [full] is needed for the unit suite imports
python -m pytest tests/unit/ --ignore=tests/data -q --timeout=120
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
# Provider API Keys (at least one required - all optional individually)
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
- **OpenAI** - Best for deep research (o3/o4-mini)
- **Gemini** - Best value (excellent quality at low cost)
- **Grok** - Cheapest ($0.01/query), great for web search and news
- **Anthropic** - Best for complex reasoning and coding

**Recommended (two keys):** OpenAI + Grok or Gemini + Grok. This gives you deep research *and* a cheap fallback for simple queries. Auto mode routes appropriately.

**Full setup (all keys):** Auto mode has maximum flexibility - $0.01 for lookups, $0.04 for moderate queries, $0.50 for deep research. Each provider's strengths are used where they matter most.

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
deepr -h
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
- Python 3.12+ required
- May need `python3-dev` for some dependencies

### macOS
- Works on Intel and Apple Silicon
- Python 3.12+ required
- Install via Homebrew: `brew install python3`

### Windows
- Works on Windows 10/11
- Python 3.12+ required from python.org
- PowerShell or Command Prompt both supported
- Git Bash works but use native Python (not MinGW)

## Next Steps

After installation:

1. Read [Quick Start](QUICK_START.md) for basic usage
2. Explore [Feature Reference](FEATURES.md) for all features
3. Review [Examples](EXAMPLES.md) for effective prompts
4. Check [ROADMAP.md](../ROADMAP.md) for upcoming features

## Uninstall

```bash
pip uninstall deepr
```

## Getting Help

- Documentation: All markdown files in `docs/`
- Issues: https://github.com/blisspixel/deepr/issues
- Questions: Create a GitHub discussion
