# Deepr Development Roadmap

**Mission:** Research infrastructure for humans and AI agents to learn and advance at scale.

Deepr is the open-source, multi-provider platform for deep research automation. This roadmap outlines our path from adaptive planning (Level 3) toward more autonomous, self-improving research systems (Level 4-5).

## Current Status

### v2.1 - Adaptive Research Workflow (Current Release)

**Production-ready:**
- Single deep research jobs (CLI + web UI)
- OpenAI Deep Research integration (o3/o4-mini)
- Background worker with automatic polling
- Cost tracking and budget management
- SQLite queue + filesystem storage
- Web UI with real-time updates and cost analytics

**Beta (functional, use with supervision):**
- Multi-phase campaigns (`deepr prep plan/execute/continue/auto`)
- GPT-5 as research lead, reviewing and planning next phases
- Context chaining with automatic summarization
- Adaptive workflow: plan → execute → review → replan

**Experimental (functional, may change):**
- Dynamic research teams (`deepr team analyze`)
- Team assembly optimized per question
- Multiple perspectives with conflict highlighting

**Key Innovation:** Research workflows that adapt based on findings, mirroring how human research teams work.

## Agentic Levels Framework

Deepr's development follows a progression toward autonomy:

| Level | Description | Status |
|-------|-------------|--------|
| **Level 1** | Reactive Execution (single-turn) | Complete |
| **Level 2** | Procedural Automation (scripted sequences) | Complete |
| **Level 3** | Adaptive Planning (feedback-driven) | **Current (v2.1)** |
| **Level 4** | Reflective Optimization (learns from outcomes) | Target (v2.4) |
| **Level 5** | Autonomous Meta-Research (self-improving) | Vision (v3.0+) |

**Philosophy:** Quality over automation. We build trust through transparency and demonstrated quality before enabling greater autonomy.

## Near-Term Development

### v2.2 - UX & Observability (Q1 2026)

**Priority 1: Ad-Hoc Job Management**

Current limitation: Requires continuous worker process to check job status.

**Adding:**
```bash
deepr research poll <job-id>        # Check OpenAI once, download if ready
deepr research poll --all           # Update all processing jobs
deepr queue refresh                 # Sync entire queue with OpenAI
```

**Benefits:**
- Daily check-ins without running worker 24/7
- CI/CD integration (check job in pipeline)
- Ad-hoc usage patterns
- Lower resource usage for casual users

**Priority 2: Observability & Transparency**

Make reasoning visible and auditable:

- **Metadata generation:** Auto-track prompt, context used, model, tokens, cost per task
- **Decision logs:** "GPT-5 chose Phase 2 topics because [gap analysis]"
- **Cost attribution:** Per-phase, per-perspective breakdowns
- **Reasoning traces:** Timeline view of how research evolved

**CLI additions:**
```bash
deepr research result <job-id> --explain      # Why this research path?
deepr research result <job-id> --timeline     # Reasoning evolution
deepr research result <job-id> --cost         # Detailed cost breakdown
```

**Priority 3: Human-in-the-Loop Controls**

Balance automation with oversight:

```bash
deepr prep plan "..." --review-before-execute    # Approve plan first
deepr prep pause <campaign-id>                   # Mid-campaign intervention
deepr prep edit-plan <campaign-id>               # Adjust next phase
```

**Priority 4: Provider Resilience**

- Auto-retry with fallback providers on failure
- Graceful degradation (o4-mini if o3 unavailable)
- Provider health monitoring
- Auto-resume campaigns after recovery

### v2.3 - MCP Server & Ecosystem (Q2 2026)

**Priority 1: Model Context Protocol Server**

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

**Priority 2: MCP Client (Connect to Data Sources)**

Deepr can use other MCP servers as data sources:

- Connect to Slack, Notion, filesystems via MCP
- "Research based on our internal docs" workflows
- Context injection from external sources
- Standardized data access across tools

**Priority 3: Dynamic Research Teams - Observability**

Make team perspectives visible:
- Show which team member contributed what findings
- Highlight where perspectives converge vs. diverge
- Cost breakdown per team member
- Export debate structure along with synthesis

### v2.4 - Learning & Optimization (Q3 2026)

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
- **OpenAI is the only provider with turnkey Deep Research API**
- o3-deep-research and o4-mini-deep-research
- GPT-5 for planning and review

**Architecture Ready For:**
- **Azure OpenAI** - Same models, enterprise deployment
- **Anthropic** - Extended Thinking implemented for reasoning transparency
- **Future providers** - When Google, others launch deep research APIs

**Provider Selection Strategy:**
- Default: OpenAI (most mature offering)
- Manual: `--provider openai|azure|anthropic` flag
- Future: Automatic routing based on task type and performance benchmarks
- No vendor lock-in

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

**Near-term focus (v2.2-2.3):**
- Better UX (ad-hoc job management)
- MCP server (AI agent integration)
- Observability and transparency
- Provider resilience

**Medium-term (v2.4):**
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
