# Installation Guide

Complete installation guide for Deepr on Linux, macOS, and Windows.

## Quick Install (5 minutes)

**Deepr works on Windows, macOS, and Linux** (Python 3.12+). The distribution
package is named `deepr-research`; the CLI command is `deepr`. Public packages
currently ship as verified GitHub release assets. PyPI publication is not yet
enabled.

### Recommended release install

**Windows PowerShell:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
```

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
```

The installers resolve the latest supported wheel from GitHub Releases and
install it in an isolated pipx environment. They exit without changing an
existing Deepr installation when GitHub is unreachable or the latest release
does not contain a supported wheel.

### Development or source install

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
```

### Bare / fast path

```powershell
pip install -e .
```

**Windows note:** A bare install with a global Python often puts the CLI in
`%APPDATA%\Python\Python312\Scripts`, which may not be on `PATH`. The virtual
environment or pipx paths above are preferred.

**Note on optional recon-tool:** `deepr doctor` may suggest `pip install -U recon-tool` for enhanced native domain intelligence in experts. This is **optional** - not a hard dependency. It adds passive DNS recon when available.

### Step 2: Configure Capacity

```bash
# Copy example configuration
cp .env.example .env

# Edit configuration file
# Linux/macOS: nano .env
# Windows: notepad .env
# Or use any text editor
```

Deepr can start with local Ollama, explicit plan-quota CLIs, metered API keys,
or any mix of those. Add API keys only when you want metered cloud providers:

```bash
# Metered cloud capacity. Pick any one to start, or use none for local/plan
# workflows. Additional keys enable explicit bounded provider choices;
# automatic cross-provider metered fallback is gated in v2.36.

OPENAI_API_KEY=sk-...       # GPT-5.5/5.4 families + o3/o4-mini deep research
GEMINI_API_KEY=...          # Gemini text/multimodal; managed Deep Research is gated
XAI_API_KEY=xai-...         # Grok 4.3, Grok 4.20, explicit premium image calls
ANTHROPIC_API_KEY=...       # Claude Sonnet 5, Opus 4.8, Fable 5, Haiku 4.5

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
# Free preflight
deepr research "What is 2+2?" --provider openai --model o4-mini-deep-research --preview

# One bounded live query
deepr research "What are the latest developments in quantum computing?" --provider openai --model o4-mini-deep-research --budget 2

# Bounded xAI text without unpriced server-side tools
deepr research "Explain transformer architecture" --provider xai -m grok-4.3 --no-web --no-code --preview
```

That's it! You're ready to use Deepr.

## Advanced Installation

### From a GitHub release

```bash
# Download the wheel for the selected release, then install it locally.
python -m pip install ./deepr_research-2.36.2-py3-none-any.whl
deepr --version
```

Release assets are published at
<https://github.com/blisspixel/deepr/releases>. Verify the release tag and the
asset checksum shown by GitHub before installation. PyPI publication is a
separate future release channel and is not currently available.

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
docker run -e OPENAI_API_KEY=sk-... deepr research "Your query" --provider openai --model o4-mini-deep-research --preview
```

## Configuration Details

### Environment Variables

Edit `.env` file:

```bash
# Provider API Keys (optional individually; local and plan-quota workflows can
# run without them)
OPENAI_API_KEY=sk-...               # OpenAI GPT and deep research models
GEMINI_API_KEY=...                  # Google Gemini; managed Deep Research is gated
XAI_API_KEY=xai-...                 # xAI Grok text models and explicit image calls
ANTHROPIC_API_KEY=...               # Anthropic Claude models
# AZURE_OPENAI_KEY=...              # Azure OpenAI (enterprise)
# AZURE_OPENAI_ENDPOINT=...         # Azure endpoint
# AZURE_PROJECT_ENDPOINT=...        # Azure AI Foundry (enterprise deep research)

# Cost Controls
DEEPR_MAX_COST_PER_JOB=10.0         # Max cost per research job
DEEPR_MAX_COST_PER_DAY=100.0        # Daily spending limit
DEEPR_MAX_COST_PER_MONTH=1000.0     # Monthly spending limit

# Features
DEEPR_AUTO_REFINE=false             # Auto-optimize prompts before submission
DEEPR_AUTO_EVAL=false               # Explicit opt-in to cost-capped model evals
SCRAPE_MAX_RESPONSE_BYTES=8388608   # Decompressed HTTP body ceiling per page

# Storage
DEEPR_DATA_DIR=data                 # Runtime root, including data/queue/research_queue.db
DEEPR_REPORTS_PATH=data/reports     # Separate report root
# DEEPR_QUEUE_DB_PATH=queue/research_queue.db  # Optional explicit queue override
```

### Recommended Provider Setup

**Minimum:** run `deepr init` and `deepr doctor`. A local Ollama model or an
explicit admitted plan-quota CLI can support `$0` marginal-cost expert
maintenance without provider keys. For API-backed research, any single provider
key works.

Pick based on your priority:
- **OpenAI** - Deep research and GPT synthesis/planning
- **Gemini** - Large-context and multimodal workflows
- **Grok** - Freshness-oriented Grok text models and explicit premium images
- **Anthropic** - Claude Sonnet 5 balance, Opus/Fable premium reasoning

**Recommended:** start with one provider key for bounded API research, or no key
for local/plan expert workflows. Add another provider only when you need an
explicit alternative. Deepr previews each bounded choice, but v2.36 does not
automatically fall through from one metered provider to another.

**All keys:** model and provider metadata becomes visible for explicit selection.
This does not enable managed Deep Research agents, multi-agent research, hosted
file/vector context, or automatic metered fallback while their complete cost
transactions remain gated.

**For enterprise:**
- Use a fully priced bounded Azure OpenAI request where its deployment and tool
  envelope is supported. Azure AI Foundry Agent/Thread/Run execution is gated
  in v2.36; its metadata and deployment guidance do not imply dispatch.
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

# Test bounded planning without a provider call
deepr research "What is 2+2?" --provider openai --model o4-mini-deep-research --preview

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
