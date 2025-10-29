# Deepr Development Roadmap

**Mission:** Research infrastructure for humans and AI agents to learn and advance at scale.

Deepr is the open-source, multi-provider platform for deep research automation. This roadmap outlines our path from adaptive planning (Level 3) toward more autonomous, self-improving research systems (Level 4-5).

## Current Status

### v2.2 - File Upload & Prompt Refinement (Released October 2025)

**Production-ready (tested in real usage):**
- Single deep research jobs (CLI + web UI)
- **File upload with vector store support** (PDF, DOCX, TXT, MD, code files)
- **Automatic prompt refinement** (--refine-prompt flag adds date context, structure, clarity)
- OpenAI Deep Research integration (o3-deep-research, o4-mini-deep-research models)
- Background worker with automatic polling
- Cost tracking and budget management
- SQLite queue + filesystem storage
- Web UI with real-time updates and cost analytics

**Beta (functional, use with supervision):**
- Multi-phase campaigns (`deepr prep plan/execute/continue/auto`)
- GPT-5 (or latest OpenAI flagship) as research lead, reviewing and planning next phases
- Context chaining with automatic summarization
- Adaptive workflow: plan → execute → review → replan

**Experimental (functional, may change):**
- Dynamic research teams (`deepr team analyze`)
- Team assembly optimized per question
- Multiple perspectives with conflict highlighting

**Key Innovation:** File upload enables semantic search over uploaded documents, eliminating the need for text injection workarounds.

## Agentic Levels Framework

Deepr's development follows a progression toward autonomy:

| Level | Description | Status |
|-------|-------------|--------|
| **Level 1** | Reactive Execution (single-turn) | Complete |
| **Level 2** | Procedural Automation (scripted sequences) | Complete |
| **Level 3** | Adaptive Planning (feedback-driven) | **Current (v2.3)** |
| **Level 4** | Reflective Optimization (learns from outcomes) | Target (v2.5) |
| **Level 5** | Autonomous Meta-Research (self-improving) | Vision (v3.0+) |

**Philosophy:** Quality over automation. We build trust through transparency and demonstrated quality before enabling greater autonomy.

## Near-Term Development

### v2.3 - Observability & UX Improvements (In Development - October 2025)

**Status:** Implementation complete, testing in progress. Most features functional but need validation in production scenarios.

**Priority 1: File Upload Enhancements - Implemented (needs testing)**

Vector store management commands implemented:

```bash
# Persistent vector stores for reuse
deepr vector create --name "company-knowledge" --files docs/*.pdf
deepr vector list
deepr vector info <vector-store-id>
deepr vector delete <vector-store-id>
deepr research submit "Query" --vector-store company-knowledge --yes
```

**Implemented:**
- Vector store CRUD operations
- Reuse across jobs
- ID/name lookup

**Known limitations:**
- Not tested with large file sets
- Error handling needs validation
- Performance with many stores unknown

**TODO:**
- ZIP archive support
- Comprehensive testing
- Performance optimization

**Priority 2: Prompt Refinement Enhancements - Implemented (needs testing)**

```bash
# Dry-run mode
deepr research "query" --refine-prompt --dry-run

# Always-on refinement
# Add to .env: DEEPR_AUTO_REFINE=true
```

**Implemented:**
- Dry-run mode
- DEEPR_AUTO_REFINE config
- Date context injection
- Structured deliverables

**Known limitations:**
- Refinement quality varies by prompt type
- No template persistence yet
- Manual testing only

**TODO:**
- Template save/load functionality
- More refinement patterns
- Quality validation

**Priority 3: Ad-Hoc Job Management - Implemented (needs testing)**

The `deepr research get` command has been implemented to download research results without running a continuous worker.

```bash
deepr research get <job-id>          # Download specific job results from provider
deepr research get --all             # Download all completed jobs
deepr queue sync                     # Sync all jobs with provider status
```

**Implemented functionality:**
- Download specific job results by ID
- Batch download all completed jobs
- Queue synchronization with provider
- Ad-hoc polling without worker

**Known limitations:**
- Job ID lookup issues (shortened vs full UUID)
- Not tested with large job queues
- Error handling for failed downloads needs validation
- Timeout behavior not thoroughly tested

**TODO:**
- Test with various job states (pending, running, failed)
- Validate batch download with many jobs
- Improve job ID resolution
- Add progress indicators for batch operations

**Priority 4: Observability & Transparency (PARTIALLY COMPLETE)**

**Completed:**
- **Cost attribution:** `deepr research result <job-id> --cost` shows detailed breakdown
  - Token usage (input, output, reasoning)
  - Cost calculation (input cost, output cost, total)
  - Pricing information (per 1M tokens)
  - Job metadata (model, times, prompt)

**Remaining work:**
- **Decision logs:** "GPT-5 chose Phase 2 topics because [gap analysis]"
- **Reasoning traces:** Timeline view of how research evolved

**CLI additions (planned):**
```bash
deepr research result <job-id> --explain      # Why this research path? (planned)
deepr research result <job-id> --timeline     # Reasoning evolution (planned)
```

**Priority 5: Human-in-the-Loop Controls - Implemented (needs testing)**

**Implemented:**
- **Review before execution:** `deepr prep plan "..." --review-before-execute`
  - Tasks start as unapproved when flag is used
  - Requires explicit human approval via `deepr prep review`
  - Prevents autonomous execution without oversight
- **Pause/Resume campaigns:** Mid-campaign intervention
  - `deepr prep pause` - Pause active campaign
  - `deepr prep resume` - Resume paused campaign
  - Execute command checks pause status before running

**Known limitations:**
- Not tested with multi-phase campaigns
- Pause state persistence not validated
- Resume behavior after errors unclear
- Review workflow only manually tested

**TODO:**
- Test pause/resume across campaign phases
- Validate state persistence after restarts
- Add tests for edge cases (pause during execution)
- Implement plan editing before resume

**Future enhancements (planned):**
```bash
deepr prep edit-plan <campaign-id>   # Modify plan before resuming (planned)
```

**Priority 6: Provider Resilience - Implemented (needs testing)**

**Implemented:**
- **Auto-retry with exponential backoff**
  - 3 retry attempts with 1s, 2s, 4s delays
  - Handles rate limits, connection errors, timeouts
- **Graceful degradation**
  - o3-deep-research → o4-mini-deep-research fallback
  - Automatic model downgrade on persistent failures
  - Aims to ensure research completes even if preferred model unavailable

**Known limitations:**
- Retry logic not tested under actual rate limits
- Fallback behavior not validated in production
- No metrics on retry success rates
- Unclear how it handles partial failures

**TODO:**
- Test retry behavior with actual API rate limits
- Validate graceful degradation under failures
- Add retry/fallback metrics and logging
- Test with various error conditions

**Future enhancements:**
- Provider health monitoring dashboard
- Auto-resume campaigns after recovery
- Multi-provider failover (OpenAI → Anthropic → Google)

### v2.4 - MCP Server & Expert Capability (Q2 2026)

**Priority 1: Deepr Expert - Chat with Research (Research in progress)**

Enable conversational access to accumulated research findings:

```bash
deepr expert chat                          # Interactive chat with all research
deepr expert export --format zip           # Export knowledge package
```

**Vision:**
- Chat interface that leverages temporal knowledge graphs of all research
- AI agent with access to full research history and context
- Export comprehensive knowledge packages (ZIP with all findings, citations, perspectives)
- Use exported packages in any LLM/RAG/agentic setup

**Research questions (in progress):**
- How to use temporal knowledge graphs to organize and validate research findings?
- Best practices for building TKGs from research outputs?
- Architecture for chat agent with full research context?
- Export format for maximum compatibility with LLM/RAG systems?

**Status:** Research phase - investigating TKG approaches, validation methods, and export formats

**Priority 2: Model Context Protocol Server**

Enable AI agents and tools to use Deepr as a research capability:

```bash
deepr mcp serve                    # Start MCP server (stdio or HTTP)
deepr mcp serve --transport http   # Network-accessible MCP server
```

**MCP Tools Exposed:**
- `start_research(query, context)` → Returns job_id
- `get_report(job_id)` → Returns markdown report
- `list_jobs()` → Returns job queue
- `cancel_job(job_id)` → Cancels running job

**Agent Integration:**
- Claude Desktop, Cursor, Windsurf can call Deepr
- Agents autonomously submit research and retrieve reports
- Long-running jobs supported via MCP notifications
- Progress updates streamed to clients

**Priority 3: MCP Client (Connect to Data Sources)**

Deepr can use other MCP servers as data sources:

- Connect to Slack, Notion, filesystems via MCP
- "Research based on our internal docs" workflows
- Context injection from external sources
- Standardized data access across tools

**Priority 4: Dynamic Research Teams - Observability**

Make team perspectives visible:
- Show which team member contributed what findings
- Highlight where perspectives converge vs. diverge
- Cost breakdown per team member
- Export debate structure along with synthesis

### v2.5 - Learning & Optimization (Q3 2026)

**Moving toward Level 4: System learns from outcomes**

**Priority 1: Research Library & Discovery**

```bash
deepr library search "EV market"           # Semantic search past research
deepr library info <job-id>                # Detailed metadata + quality signals
```

**Discovery, not automatic reuse:**
- Find related past research
- Show: date, cost, model, user rating, perspective
- User reads, judges quality, decides to reuse
- Explicit `--reuse-context job-123` flag (high friction by design)
- Default: always fresh research

**Why conservative:** Context quality determines research quality. Bad context = bad research. Better to over-research than confidently deliver garbage.

**Priority 2: Quality Metrics & Benchmarking**

Track what works:
- Citation quality scores
- User ratings per report
- Cost/value ratios
- Provider performance by task type
- Rolling 30-day stats

Use for:
- Automatic provider routing (best tool for each task)
- Research strategy optimization
- Quality regression detection

**Priority 3: Basic Verification**

Start simple:
- Internal contradiction detection
- Citation coverage metrics
- Confidence scoring per claim
- Flag low-confidence sections for human review

**Priority 4: Platform Integrations**

- Export to Notion, Obsidian, Airtable
- Slack/Teams notifications for campaign completion
- Webhook support for custom workflows
- REST API improvements for programmatic access

## Long-Term Vision

### v3.0+ - Autonomous Expertise Acquisition (Level 5)

**Vision: Self-directed learning until mastery achieved**

Level 5 isn't about consciousness - it's about **autonomous expertise acquisition**. The system becomes expert on any topic through self-directed research.

**The Autonomous Learning Loop:**

```
User: "Become expert on quantum computing commercialization"

Agent Loop (autonomous):
  1. Identify knowledge gaps
     "I understand market overview but weak on supply chain"

  2. Research gaps autonomously
     Executes targeted research without human direction

  3. Run validation (PhD Defense simulation)
     Panel of simulated experts challenges understanding:
     - "Explain superconducting qubit stability trade-offs"
     - "Reconcile technical timeline with market projections"
     - "What are the three biggest commercialization risks?"

  4. If gaps found → Research more → Try again
     If comprehensive → Pass → Present with humility

  5. Present findings with beginner's mind
     "I've researched this comprehensively and validated
     understanding through adversarial review. Here's what
     I know... But I may have blind spots. Ask me anything,
     and if I don't know, I'll research it."
```

**Key Characteristics:**

1. **Perceive** - Agent detects gaps in own understanding ("I don't know X")
2. **Plan** - Autonomously decides what to research next based on gaps
3. **Execute** - Runs research without human direction
4. **Evaluate** - Validates comprehension through simulated expert panel
5. **Improve** - Continues until expertise passes validation

**Not consciousness, but self-directed learning.** The agent identifies what it doesn't know and figures it out autonomously.

**PhD Defense Validation:**

Simulated expert panel challenges agent's understanding:
- Adversarial questioning surfaces gaps
- Agent must demonstrate comprehensive knowledge
- Can't just memorize - must explain and defend
- Fails if gaps found, researches more, tries again
- Passes when understanding withstands scrutiny

Implementation via Constitutional AI: Encode assessment rules ("admit uncertainty", "provide reasoning steps") in model constitution, enabling self-critique and calibrated confidence (e.g., ECE < 5%, accuracy ≥95%).

**Humble Expertise:**

Even after validation, maintains beginner's mind:
- Confident about researched areas
- Transparent about methodology
- Admits potential blind spots
- Willing to research more if challenged
- "I understand this comprehensively, but contexts change"

**Key Features:**

**Autonomous Gap Identification:**
- After each research round, agent evaluates own understanding
- Identifies specific knowledge gaps
- Generates targeted research questions autonomously
- Continues until no major gaps remain

**Mock Conversations for Blind Spot Detection:**
- Simulated board discussions between perspectives
- Devil's advocate challenges assumptions
- Cultural or domain-specific viewpoints
- Conflicts reveal areas needing deeper research

**Validation Mechanisms:**
- PhD defense simulation (adversarial expert panel)
- Multi-provider consistency checks
- Citation confidence scoring
- Internal contradiction detection
- Self-assessment: "Do I understand this comprehensively?"

**Practical Applications:**
- Meeting prep: "Research customer's industry" (10 min, $2)
- Strategic planning: "Become expert on market dynamics" (60 min, $8)
- Due diligence: "Comprehensive analysis with validation" (2 hours, $15)
- Any depth needed, from quick brief to PhD-level expertise

**Smart Context Management:**
- "What's new since last research?" delta updates
- Incremental research vs. full re-research
- Knowledge freshness tracking
- Temporal awareness (market data vs. fundamentals)

**Multi-Tenancy & Scale:**
- Team workspaces with shared research libraries
- Access control and permissions
- Usage analytics per team/user
- Enterprise deployment options

## Multi-Provider Strategy

**Current Reality (October 2025):**

Multiple providers now offer deep research capabilities:

- **OpenAI**: GPT-5 family with Deep Research API (o3-deep-research, o4-mini-deep-research)
- **Anthropic**: Claude Opus 4.1, Sonnet 4.5, Haiku 4.5 with Web Search tools
- **Google**: Gemini 2.5 Pro/Flash/Flash-Lite with Deep Research (Enterprise+)
- **xAI**: Grok 4 and Grok 4 Fast with agentic tool-calling
- **Azure OpenAI**: GPT-5 family via Azure AI Foundry (enterprise deployment)

**Provider Selection Strategy:**
- Current: OpenAI Deep Research API (most mature, turnkey solution)
- Manual: `--provider openai|azure|anthropic|google|xai` flag
- Planned: Automatic routing based on task type, cost, and performance
- Architecture: Provider-agnostic design, no vendor lock-in

**Deepr's Value Beyond Single-Provider Wrappers:**
- Intelligent multi-phase planning with context chaining
- Adaptive workflows (plan → execute → review → replan)
- Dynamic research teams with diverse perspectives
- Provider-agnostic architecture with automatic routing
- MCP integration for ecosystem compatibility

## Design Principles

**Quality Over Automation:**
- Bias toward fresh research and human judgment
- High friction for context reuse (quality preservation)
- Transparent by default
- Autonomous where proven reliable

**CLI First, Multi-Interface:**
- Command-line primary for power users
- Web UI for interactive use
- MCP server for AI agent integration
- REST API for programmatic access

**Local-First, Provider-Agnostic:**
- SQLite queue (no external database required)
- Filesystem storage (no cloud dependency)
- Multi-provider support (no vendor lock-in)
- Open standards (MCP, JSON-RPC)

**Observability Enables Trust:**
- Make reasoning visible before making it autonomous
- Full audit trails available on demand
- Cost transparency per task/phase/provider
- Explain decisions in natural language

**Open Ecosystem:**
- Standard protocols (MCP)
- Plugin architecture (planned)
- Community-driven templates and patterns
- Extensible for custom workflows

## Use Cases at Scale

**For Humans:**
- Market analysis and competitive intelligence
- Technical due diligence with dependencies
- Strategic planning with comprehensive context
- Academic research with citation management

**For AI Agents:**
- On-demand deep research capability via MCP
- Grounding LLM reasoning in fresh, cited data
- Multi-step knowledge gathering for complex tasks
- Autonomous research in agentic workflows

**For Teams:**
- Shared research libraries with semantic search
- Collaborative multi-phase campaigns
- Cost-effective alternative to consulting fees ($3-5 vs. $5,000+)
- Continuous learning and knowledge building

## Non-Goals

Explicitly NOT building:
- Chat interface (use regular LLMs)
- Real-time responses (deep research takes time by design)
- Sub-$1 research (comprehensive research has real cost)
- Mobile apps (CLI/web/MCP sufficient)
- Features without clear value
- Vendor lock-in or proprietary extensions

## Contributing

High-impact areas:
- Context chaining logic and prompt engineering
- Synthesis strategies for integrating findings
- Cost optimization techniques
- Template patterns for common research workflows
- Provider integrations
- MCP server implementation
- Documentation and examples

Most valuable work is on the intelligence layer (planning, context management, synthesis) rather than infrastructure.

## Dogfooding

We use Deepr to build Deepr. Recent examples:

- **Context injection best practices** ($0.17, 6 min) - Validated our ContextBuilder design, informed Phase 2 prompt engineering
- **MCP protocol research** ($0.18, 10 min) - Comprehensive analysis of MCP architecture and strategic value for Deepr
- **Competitive landscape** ($0.13) - Identified gaps vs. Elicit, Perplexity, Consensus, SciSpace

This validates the tool while generating implementation guidance. When we hit design questions, we research them using Deepr itself.

---

## Summary

Deepr is evolving from an adaptive planning system (Level 3) toward a self-improving research platform (Level 4-5) that serves both humans and AI agents.

**Near-term focus (v2.3-2.4):**
- Testing and validating v2.3 implementations
- Prompt refinement improvements
- Better UX (ad-hoc job management, observability)
- MCP server (AI agent integration)
- Provider resilience validation

**Medium-term (v2.5):**
- Learning from outcomes
- Quality metrics and benchmarking
- Basic verification
- Platform integrations

**Long-term (v3.0+):**
- Continuous learning and optimization
- Advanced verification
- Multi-tenancy and scale
- Platform maturity

**Core principle:** Build research infrastructure that enables humans and AI systems to learn and advance at scale. Quality and trust over hype and automation.
