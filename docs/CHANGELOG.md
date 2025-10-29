# Changelog

All notable changes to Deepr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - v2.3

### Added

**Always-On Prompt Refinement**
- Added `DEEPR_AUTO_REFINE` configuration option in .env
- When enabled, automatically applies prompt refinement to all research submissions
- No need to specify `--refine-prompt` flag each time
- Provides seamless best practices for all queries

**Campaign Pause/Resume Controls**
- Added `deepr prep pause` command to pause active research campaigns
- Added `deepr prep resume` command to resume paused campaigns
- Execute command now checks pause status before running
- Enables mid-campaign intervention for human oversight
- Supports both specific plan IDs and most recent campaign

**Persistent Vector Store Management**
- Added `deepr vector create` command to create reusable vector stores
- Added `deepr vector list` command to list all vector stores
- Added `deepr vector info` command to show vector store details
- Added `deepr vector delete` command to remove vector stores
- Added `--vector-store` flag to `deepr research submit` for reusing existing stores
- Vector stores can be looked up by ID or name
- Enables document indexing once, reuse across multiple research jobs

**Batch Job Download and Queue Sync**
- Added `--all` flag to `deepr research get` for downloading all completed jobs
- Added `deepr queue sync` command to update all job statuses without downloading
- Automatically checks provider for all pending jobs and downloads completed ones
- Useful for batch processing after submitting multiple research jobs
- Queue sync updates local status to match provider without downloading results

**Enhanced Cost Management**
- Added `--period` flag to `deepr cost summary` (today, week, month, all)
- Cost breakdown by model showing per-model spending and job counts
- Budget tracking with percentage of daily/monthly limits
- Improved statistics with total jobs, completed count, and averages

**Research Export**
- Added `deepr research export` command for exporting in multiple formats
- Supports markdown, txt, json, and html export formats
- Automatic output path generation or custom output location
- Includes job metadata, content, and usage statistics in exports

**Build and Installation**
- Added pyproject.toml for modern Python packaging
- Created INSTALL.md with platform-specific instructions
- Added install scripts for Linux/macOS (install.sh) and Windows (install.bat)
- Added Makefile for common development tasks
- Added build scripts (build.bat for Windows)
- Updated setup.py to version 2.3.0
- Console script entry point enables `deepr` command globally

**Configuration Management**
- Added `deepr config validate` command to check configuration and API connectivity
- Added `deepr config show` command to display current settings (sanitized)
- Added `deepr config set` command to update configuration values
- Validates API keys, directories, and budget limits
- Tests provider connectivity during validation

**Analytics and Insights**
- Added `deepr analytics report` command for usage analytics
- Success rates, model performance, cost analysis by time period
- Added `deepr analytics trends` showing daily job counts and costs
- Added `deepr analytics failures` for failure pattern analysis
- Identifies most cost-effective models and provides recommendations

**Prompt Templates**
- Added `deepr templates save` to save reusable prompts with placeholders
- Added `deepr templates list` to view all saved templates
- Added `deepr templates show` to display template details
- Added `deepr templates delete` to remove templates
- Added `deepr templates use` to submit research using templates
- Tracks usage count for each template
- Supports placeholder substitution (e.g., {industry}, {region})

### Changed
- Execute command now prevents execution of paused campaigns
- Improved human-in-the-loop controls with pause/resume workflow
- Research submit command now supports both new file uploads and existing vector stores
- Simplified README Quick Start to focus on pip install workflow

## [2.2.0] - 2025-10-29

### Added

**File Upload & Vector Stores**
- Added `--files` / `-f` flag to `deepr research submit` for document upload
- Automatic vector store creation and indexing for semantic search
- Support for PDF, DOCX, TXT, MD, and code files
- Successfully tested with multi-document research workflows

**Automatic Prompt Refinement**
- Added `--refine-prompt` flag to optimize research queries automatically
- Uses GPT-5-mini to enhance prompts with temporal context and structure (~$0.001 per refinement)
- Automatically adds current date context ("As of October 2025...")
- Suggests structured deliverables and flags missing business context
- Provides before/after comparison of prompt improvements

**Ad-Hoc Result Retrieval**
- Added `deepr research get <job-id>` command for on-demand result downloads
- Check provider status and download results without continuous worker
- Perfect for daily check-ins, CI/CD integration, and casual usage
- Eliminates need for 24/7 worker process

**Detailed Cost Breakdowns**
- Added `--cost` flag to `deepr research result` command
- Shows comprehensive token usage breakdown (input/output/reasoning)
- Displays separate cost calculations for input and output tokens
- Includes model pricing information (per 1M tokens)
- Shows job metadata and prompt context

**Human-in-the-Loop Controls**
- Added `--review-before-execute` flag to `deepr prep plan` command
- Tasks start unapproved when flag is used, requiring explicit human approval
- Prevents autonomous execution without oversight
- Use `deepr prep review` to approve/reject tasks before execution

**Provider Resilience**
- Implemented retry logic with exponential backoff (3 attempts: 1s, 2s, 4s delays)
- Graceful degradation: automatically falls back from o3-deep-research to o4-mini-deep-research
- Handles rate limits, connection errors, and timeouts automatically
- Ensures research completes even if preferred model is unavailable

### Changed

**CLI Commands**
- Renamed `poll` to `get` for clearer intent (retrieve results)
- Improved command descriptions and help text across all commands
- Enhanced error messages with actionable guidance

**Documentation**
- Restructured README Quick Start with clear numbered steps
- Added prerequisites section (Python 3.9+, Node.js 16+)
- Added "Why Deepr?" value proposition with key differentiators
- Clarified target audience (researchers, analysts, product teams, developers, AI agents)
- Added cost warning and budget management guidance
- Updated all time/cost estimates to "Estimated: ~$X" format
- Added descriptive context before code example sections
- Fixed grammar issues ("becoming an expert", improved wording)
- Updated Multi-Provider Support section with current October 2025 models
- Removed all emojis from documentation

**ROADMAP**
- Updated from v2.1 to v2.2 release status
- Marked priorities 1-6 as complete or partially complete
- Added implementation details for each completed feature
- Clarified model references (GPT-5, o3-deep-research, o4-mini-deep-research)
- Updated version timeline (v2.3, v2.4, v2.5)
- Updated Agentic Levels table to reflect current progress

### Fixed
- Fixed version inconsistencies throughout documentation (v2.1 → v2.2)
- Fixed port references (backend: 5000, frontend: 3000)
- Corrected model naming for clarity
- Improved Unicode handling in CLI output for Windows compatibility

### Meta-Research
- Used Deepr itself to analyze README and ROADMAP for refinement opportunities
- Applied 12+ specific recommendations from research report
- Research cost: $2.00 for comprehensive documentation review
- Demonstrated platform capabilities through self-improvement

## [2.1.0] - 2025-10-XX

### Added
- Multi-phase research campaigns with adaptive planning
- GPT-5 as research lead for reviewing and planning phases
- Context chaining with automatic summarization
- Dynamic research teams (experimental)
- Web UI with real-time updates and cost analytics

### Changed
- Improved background worker with stuck job detection
- Enhanced cost tracking from OpenAI token usage

## [2.0.0] - 2025-10-XX

### Added
- Initial release of Deepr
- Single deep research jobs via CLI
- OpenAI Deep Research integration (o3, o4-mini models)
- SQLite queue and filesystem storage
- Background worker with automatic polling
- Basic web UI

---

For more details on upcoming features, see [ROADMAP.md](ROADMAP.md).
