# Deepr Development Roadmap

## Model Strategy

**Dual Provider Architecture: Deep Research + Fast Models**

Deepr uses a hybrid approach optimizing for both **quality** and **cost**:

### Deep Research (OpenAI/Azure)
- **Models**: o4-mini-deep-research, o3-deep-research
- **Use cases**: Novel problem-solving, critical decisions, complex synthesis
- **Cost**: $0.50-$5.00 per query
- **Execution**: Async
- **When**: ~20% of operations requiring extended reasoning

### Fast/General Operations (xAI, Gemini, Anthropic)
- **Models**: grok-4-fast (xAI), gemini-2.5-flash (Google), claude-sonnet-4-5 (Anthropic)
- **Use cases**: News, docs, team research, learning, expert chat, planning
- **Cost**: $0.0005-$0.003 per query (96-99% cheaper!)
- **Execution**: Immediate
- **When**: ~80% of operations

### Planning & Orchestration (GPT-5)
- **Models**: gpt-5, gpt-5-mini, gpt-5-nano
- **Use cases**: Research planning, curriculum generation, adaptive workflows
- **Cost**: $0.01-$0.05 per plan
- **Execution**: Immediate
- **When**: Planning before execution

**Cost Optimization**: Using fast models for 80% of operations reduces total costs by ~90% with comparable quality for those use cases.

See [docs/MODEL_SELECTION.md](docs/MODEL_SELECTION.md) for detailed strategy.

---

## Structured Learning Approach

**Philosophy**: Real learning is not a single activity - it's a structured workflow.

Deepr standardizes four types of knowledge artifacts, each with file naming conventions:

### The Four Types

| Type | Pattern | Purpose | Model | Cost |
|------|---------|---------|-------|------|
| **news-{topic}.md** | Latest developments, releases, vulnerabilities | grok-4-fast | ~$0.001 |
| **docs-{topic}.md** | Fundamentals, APIs, official documentation | grok-4-fast | ~$0.002 |
| **research-{topic}.md** | Deep analysis, problem-solving | o4-mini OR grok-4-fast | $0.001-$0.50 |
| **team-{topic}.md** | Strategic discussions, multiple perspectives | grok-4-fast | ~$0.005 |

### Learning Cycle

```
1. NEWS (Daily)          - What's changing?
2. DOCS (As needed)      - What are the fundamentals?
3. RESEARCH (Deep dive)  - How does it work? Trade-offs?
4. TEAM (Strategic)      - Should we adopt it? What are risks?
5. EXPERT (Synthesis)    - Feed all artifacts to expert for Q&A
6. Back to NEWS          - Stay current
```

**Example learning Kubernetes**:
1. `news-kubernetes.md` - Weekly updates ($0.001)
2. `docs-kubernetes-core.md` - Core concepts ($0.002)
3. `research-kubernetes-networking.md` - Deep dive ($0.50)
4. `team-kubernetes-hosting-decision.md` - EKS vs self-host ($0.005)

**Total**: ~$0.51 for complete learning package

See [docs/LEARNING_WORKFLOW.md](docs/LEARNING_WORKFLOW.md) for comprehensive guide.

---

## Vision: Intelligent Research Automation

Deepr is research automation that thinks strategically:

**What it does:**
- Reasons about information needs
- Plans multi-phase research campaigns
- Sequences tasks based on dependencies
- Chains context across research phases
- Synthesizes insights spanning multiple findings

**What makes it intelligent:**
- Adaptive planning that adjusts based on findings
- Expert systems that learn over time
- Meta-cognitive awareness (knows what it knows vs doesn't know)
- Temporal knowledge tracking (understands when things were learned)
- Cost-aware autonomous research

This creates analysis greater than the sum of its parts through intelligent orchestration of research workflows.

## Current Status

### v2.0: Core Infrastructure (Complete)

Working now:
- SQLite queue with all operations
- Local filesystem storage
- Multi-provider support (OpenAI GPT-5, Gemini, Grok, Azure)
- **OpenAI uses GPT-5 models** (not GPT-4) for all operations
- OpenAI Deep Research integration (validated with live jobs)
- Worker: Background polling with stuck job detection (auto-cancels queued >10min)
- Cost tracking from token usage
- CLI: submit, wait, status, result, cancel, queue list/stats
- Web UI: ChatGPT-style interface (React + Vite + TailwindCSS)
  - Job queue with real-time updates
  - Cost analytics dashboard with budget tracking
  - Submit research jobs
  - Minimal monochrome design (no distracting colors)
- API: Flask REST endpoints for web UI
- Results saved as markdown with inline citations

You can submit research jobs via CLI or web UI, worker auto-polls OpenAI and downloads results when complete.

### v2.1: Adaptive Research Workflow (Beta)

The innovation: Research team workflow that adapts based on findings.

Traditional approach: Plan everything upfront, execute all at once, hope it's comprehensive.

Deepr's approach: **Plan - Execute - Review - Plan next phase**

How it works:
- GPT-5 plans Phase 1 (foundation research)
- System executes research and waits for completion
- GPT-5 reviews actual findings, identifies gaps
- GPT-5 plans Phase 2 based on what was learned
- Repeat until ready for final synthesis

This replicates how human research teams actually work:
- Team lead assigns initial research
- Team researches and reports back
- Lead reviews findings, spots gaps
- Lead assigns next round of research to fill gaps
- Continue until comprehensive

**Smart Task Mix**

The planner distinguishes between:

Documentation tasks (gather facts):
- "Document current FDA 510(k) clearance requirements and submission process"
- "Compile comprehensive list of state-specific LLC formation requirements across all 50 states"
- Purpose: Create factual reference materials
- Cheaper, faster (factual gathering)

Analysis tasks (generate insights):
- "Analyze trade-offs between leasing and buying commercial real estate for restaurant expansion"
- "Evaluate cost-effectiveness of domestic vs offshore manufacturing for our product line"
- Purpose: Synthesize information, make recommendations
- More expensive, benefits from having docs as context

Example:
```
User: "Analyze EV market"

Planner generates:
  Phase 1 (parallel):
    - Document: Latest EV sales data and projections (2025)
    - Document: Key players market share and financials
    - Research: Technology landscape and trends

  Phase 2 (uses Phase 1 context):
    - Analysis: Competitive dynamics [feeds: market data + players]
    - Analysis: Technology roadmap implications [feeds: tech landscape]

  Phase 3 (uses all):
    - Synthesis: Strategic implications [feeds: all findings]
```

**Cost-Effective Strategy (Research-Backed)**

We used Deepr to research "best practices for context injection in multi-step LLM workflows" - cost $0.17, findings directly informed this design:

- Phase 1: Mix of cheap documentation + foundational research
- Phase 2: Analysis tasks USE summarized Phase 1 context (cuts token usage by ~70%)
- Phase 3: Synthesis integrates facts AND insights
- Explicit context references: "Using the market data from Phase 1..."
- Skip obvious information or things we already have
- Reduces context dilution (focused context improves quality)
- Balance comprehensive coverage with cost control

Key insight: Summarization saves cost AND improves quality by preventing context dilution where key instructions get buried in irrelevant detail.

Status now:
- ResearchPlanner service (GPT-5 generates initial plans)
- ResearchReviewer service (GPT-5 reviews results, plans next phase)
- ContextBuilder service (gpt-5-mini summarizes for context injection)
- BatchExecutor service (orchestrates multi-phase execution)
- CLI commands:
  - `deepr prep plan` - Generate Phase 1 plan
  - `deepr prep execute` - Execute current plan
  - `deepr prep continue` - Review and plan next phase (NEW!)
  - `deepr prep auto` - Fully autonomous multi-round (NEW!)
- Phase/dependency logic working
- Context chaining implemented
- Adaptive review-and-continue workflow complete

**Real-World Example:**

```bash
# Scenario: Strategic guidance from call transcript
deepr prep auto "Review the attached call transcript with DemoCorp's CEO discussing AI strategy. Research DemoCorp's current position, competitive landscape, and provide strategic recommendations for next 12 months." --rounds 3 --context "$(cat call_transcript.txt)"

# What happens:
# Round 1 (Foundation - GPT-5 plans):
#   - Research DemoCorp's AI capabilities and market position
#   - Research competitors' AI strategies
#   - Research technologies mentioned in call
#   [Executes 3 jobs, ~15 min]

# Round 2 (Analysis - GPT-5 reviews Round 1, plans next):
#   - "Based on Round 1, DemoCorp is weak in ML infrastructure but strong in data"
#   - Research infrastructure catch-up options
#   - Research data monetization strategies
#   [Executes 2-3 jobs, ~15 min]

# Round 3 (Synthesis - GPT-5 reviews everything):
#   - Strategic roadmap leveraging data strength
#   - Implementation plan addressing infrastructure gap
#   - Risk mitigation based on competitive position
#   [Executes 1 synthesis job, ~10 min]

# Result: Comprehensive strategic guidance grounded in research + call insights
# Cost: ~$3-5
```

This is **agentic AI with research depth** - not just reasoning, but researching between reasoning steps.

**NEW: Agentic Documentation Analysis**

`deepr docs analyze <path> <scenario>` - Fully agentic workflow:
1. User points to ANY docs location
2. Agent scans and analyzes with GPT-5
3. Agent identifies gaps for the scenario
4. Agent generates research plan
5. User approves
6. Agent executes and saves results

This is properly dynamic - works anywhere, adapts to any scenario.

**Dogfooding Lesson - Context Management is Critical:**

We used Deepr to research "how to improve Deepr" without providing context about what Deepr actually is. Result: The AI found unrelated crypto projects named "Deepr.fun" and "Deepr Finance" instead of analyzing our platform. Cost: $0.36 to learn what we already knew.

**The lesson:** Context injection is THE critical feature. Without it, research goes completely off-target. We immediately updated the README to emphasize context management best practices and added concrete examples of bad vs good prompting.

This is proper dogfooding - using your product, finding real failure modes, fixing the product based on learnings.

We also successfully researched the competitive landscape (Elicit, Perplexity, Consensus, SciSpace) and identified key gaps: no integrated workflows, no developer extensibility, no collaboration features. That research was valuable ($0.13 well spent).

## Building Next: Planner Enhancements & Observability

**WARNING: Doc Reuse Intelligence** (Priority 1 - IMPLEMENTED BUT DISABLED)

Implemented doc checker but discovered fundamental limitation - DISABLED BY DEFAULT:

The Problem:
- GPT-5 sees 500 char preview + filename, can't judge actual research depth
- False confidence: "We have a doc" != "We have PhD-level comprehensive research"
- Wrong optimization: Saves money but may deliver shallow results
- Testing revealed: suitable for API docs, NOT for deep research

Implementation exists:
```python
class DocReviewer:
    def review_docs(self, scenario: str) -> Dict:
        # Scans docs/ directory
        # GPT-5 evaluates with limited context
        # RISK: Can't judge depth from preview
```

Current Status:
- Disabled by default
- `--check-docs` flag with warning
- Only use for factual/API documentation
- NOT recommended for comprehensive research

Lesson Learned:
- Premature optimization that may hurt quality
- "Does doc exist?" is wrong question for deep research
- Right question: "Is research comprehensive enough?" (can't answer from preview)
- Better to over-research than under-research with false confidence

**Planner Enhancements** (Priority 2)

Task mix improvements (already implemented):
- Distinguish documentation vs analysis tasks
- Cost-awareness (docs ~30% cheaper)
- Different prompts for each type

Additional needed:
- Skip obvious/low-value tasks
- Better dependency reasoning
- Cost-benefit analysis per task

**Market Context** (As of October 2025)

Provider landscape for Deep Research:
- **OpenAI**: **ONLY provider with turnkey Deep Research API**
  - Models: o3-deep-research, o4-mini-deep-research
  - Submit query - get comprehensive report (asynchronous)
  - Our primary execution engine

- **Azure OpenAI**: Enterprise version with Bing Search integration
  - Uses OpenAI's o3-deep-research backend
  - Integrated into Azure AI Foundry Agent Service

- **Google Gemini**: Has "Deep Research" in consumer product
  - **NOT available as API** for developers (Oct 2025)
  - Batch API is for parallel tasks, not deep research

- **Anthropic Claude**: Extended Thinking + Agent SDK
  - **NO Deep Research API equivalent**
  - DIY framework - you manage research loop yourself
  - Useful for reasoning transparency, not turnkey research

- **Perplexity/Cohere**: Different use cases (real-time search, RAG components)

**The Truth About Multi-Provider Support**

Research finding (from our own dogfooding):
> "OpenAI's Deep Research API is the seminal offering in this category... OpenAI and Microsoft Azure are the definitive leaders in this category, offering tightly integrated and powerful services that set the benchmark for the industry."

**Current Reality:**
- OpenAI is the ONLY provider with API access to deep research (Oct 2025)
- We built multi-provider architecture anticipating competitors would follow
- As of now, no alternatives exist via API

**Our Position:**
- **Multi-provider architecture** supporting OpenAI, Google Gemini, xAI Grok, Azure OpenAI
- **When using OpenAI or Azure: GPT-5 models ONLY** (gpt-5, gpt-5-mini, gpt-5-nano)
  - No GPT-4 support - GPT-5 is the standard for all OpenAI-based features
  - Expert systems: GPT-5 with tool calling for RAG (NOT deprecated Assistants API)
  - Research planning: GPT-5 for curriculum generation and adaptive workflows
  - Expert chat: GPT-5 with tool-based vector store retrieval
- Deep Research execution: OpenAI Deep Research API (o3/o4-mini-deep-research)
- Alternative providers (Gemini, Grok) supported for research tasks
- Architecture ready for future providers when they arrive

**What About Anthropic?**
- Implemented Extended Thinking provider for reasoning transparency
- Useful for analysis tasks requiring visible thought process
- NOT a replacement for Deep Research
- Could be used for planning role (GPT-5 alternative)

**Our Unique Value** (beyond single-provider wrappers):
- Intelligent multi-phase planning with context chaining
- Smart mix of documentation + analysis tasks
- Doc reuse to minimize cost
- Adaptive workflows (Plan - Execute - Review - Replan)
- Dream team dynamics (diverse cognitive perspectives)
- All via simple CLI (no complex orchestration needed)

**Future Vision:**
When other providers launch Deep Research APIs, Deepr will intelligently route:
- Quick documentation - o4-mini (fast, cheap)
- Deep analysis - o3 or competitor equivalent
- Planning - GPT-5 or Claude Extended Thinking
- Auto-fallback if provider unavailable

Testing:
- Generate plans for various scenarios
- Validate doc reuse logic works
- Measure cost savings from reusing docs
- Use Deepr itself to research optimal strategies

## Toward Agentic Level 5 (Aspirational)

**Vision:** Transform Deepr from an adaptive planning system into a self-improving meta-researcher.

**Important caveat:** This is aspirational. We're building toward these capabilities incrementally. The framework below describes where we want to go, not where we are today.

**Agentic Levels Framework:**

| Level | Description | Deepr Status |
|-------|-------------|--------------|
| 1 | **Reactive Execution** - Single-turn, no planning | Exceeded |
| 2 | **Procedural Automation** - Scripted sequences | Exceeded |
| 3 | **Adaptive Planning** - Plans and adjusts based on feedback | **Implemented (v2.1)** |
| 4 | **Reflective Optimization** - Learns from outcomes, self-tunes | **Partial (v2.5)** |
| 5 | **Autonomous Meta-Researcher** - Self-directing, goal-defining | **Aspirational** |

**What's Actually Implemented (v2.5 - Expert Consciousness):**

The expert system now has foundational "Level 4-ish" capabilities:
- Belief formation: Experts synthesize documents into beliefs with confidence levels
- Gap awareness: Experts track what they don't know (knowledge gaps with priority)
- Continuous learning: Re-synthesis triggers after research conversations
- Manual learning: `deepr expert learn` adds knowledge on demand
- Gap filling: `deepr expert fill-gaps` proactively researches gaps
- Export/import: Package expert consciousness for sharing

This is early-stage. Unit tests pass (62 new tests). Initial real-world testing shows experts form beliefs and speak from synthesized understanding. But this hasn't been battle-tested at scale. We're not claiming Level 5 - we're building toward it.

**What Level 5 Would Actually Require (not yet implemented):**

1. **Perceive** - Detect research needs and quality gaps automatically
2. **Plan** - Generate optimal research strategies without templates
3. **Act** - Execute research with autonomous provider/task selection
4. **Evaluate** - Score outcomes, detect shallow/incorrect research
5. **Update Self** - Improve planning heuristics based on results

**Honest Assessment:**
- We have pieces of this (gap detection, autonomous research triggers)
- We don't have the full closed loop yet
- The "consciousness" metaphor is useful but don't take it too literally
- This is research-grade software, not production-ready enterprise tooling

**Roadmap Alignment:**

- **v2.5 (Current):** Expert consciousness foundation
  - Belief formation and gap tracking (done)
  - Continuous learning triggers (done)
  - Manual learning and gap filling commands (done)
  - Export/import for portability (done)

- **v2.6-2.7:** Strengthen Level 4
  - Visible thinking (show expert reasoning process)
  - Better memory (conversation history, user profiles)
  - Quality scoring (confidence calibration)

- **v3.0+:** Approach Level 5
  - Self-correcting research (detect and fix errors)
  - Cross-expert knowledge sharing
  - Autonomous goal refinement

**Critical Principle: Quality Over Automation**

- Notify, don't auto-inject (context discovery vs. blind reuse)
- Bias toward over-research, not cost savings
- Transparent by default, autonomous where proven
- Human judgment for quality, machine execution for scale

**Priorities:**
- v2.5: Expert consciousness foundation (current)
- v2.6: Visible thinking + memory improvements
- v2.7: Quality scoring + verification
- v3.0+: Approach Level 5 capabilities

**v2.2: Intelligence Layer - Transparent Automation**

Focus: Fix broken UX - Clean interface - Expose via MCP - Add observability - Optimize

**Build Order Philosophy:** Foundation - Interface - Infrastructure - Observability - Optimization

---

## Priority 1: UX & Developer Experience Polish (FOUNDATION)

**Problem:** Real-world testing (Azure Landing Zone scenario) revealed friction that blocks adoption.

**Issues Validated:**
1. Manual vector store creation breaks single-command workflow
2. Windows CLI incompatibility (Unix-isms in examples)
3. Zero progress feedback during uploads (appears frozen)
4. Inconsistent command patterns (`deepr get` vs `deepr jobs get`)
5. Provider/model flags not accepted in all modes
6. Cross-platform path handling issues (spaces, Windows paths)
7. **Stale job statuses** - `deepr list` shows old data when worker isn't running [DONE] FIXED

**Solution: Implicit Vectorization & One-Line Commands**

```bash
# This should just work - no manual vector store setup
deepr run docs "Research topic" --upload "./report.docx"

# Behind the scenes:
# 1. Upload files
# 2. Create ephemeral vector store (or reuse named store)
# 3. Wait for ingestion
# 4. Submit job with retrieval enabled
```

**Implementation:**

1. **Automatic File Handling**:
   - Detect `--upload <path>` or `--files "<glob>"`
   - Resolve paths cross-platform (Windows C:\, Unix ~/, relative paths)
   - Create ephemeral vector store by default
   - Deduplicate by content hash
   - Wait for "ready" status before submitting job

2. **Power-User Overrides**:
   ```bash
   --vector-store <id>                    # Use existing store
   --vector-store-name <name>             # Create/reuse named persistent store
   --vector-store-ephemeral               # Force ephemeral
   --vector-store-retain one-shot|days:N  # Control lifecycle
   --no-vector-store-wait                 # Don't wait for ingestion
   ```

3. **Progress Feedback**:
   - Show phases: "Uploading files...", "Creating vector store...", "Indexing...", "Submitting job..."
   - Add spinner for network waits
   - After 15 seconds: "Still working... Ctrl+C to cancel (uploads are safe)"

4. **Command Consistency**:
   - Standardize on `deepr get <job-id>` everywhere
   - Standardize on `deepr list`
   - Accept `--provider` and `--model` in ALL modes
   - Single-line examples only in docs and help
   - [DONE] `deepr list` auto-refreshes stale job statuses from provider

5. **Cross-Platform Paths**:
   - Accept quoted absolute or relative paths
   - Support Windows `C:\path\file.docx` and Unix `~/path/file.docx`
   - Normalize internally, echo resolved absolute path
   - Handle spaces in paths correctly

6. **Diagnostics Command**:
   ```bash
   deepr doctor
   # Checks:
   # - Provider API keys present and valid
   # - Network reachability
   # - File read permissions
   # - Temp/cache directory write access
   ```

**Acceptance Criteria:**
- [DONE] `deepr list` refreshes stale statuses automatically
- [TODO] `deepr run focus "..." --upload "path/with spaces/file.docx"` works without prior setup
- [TODO] All commands print clear progress phases
- [TODO] `--provider` and `--model` work in all modes
- [TODO] All README examples are single-line and cross-platform tested
- [TODO] Paths with spaces work on Windows CMD, PowerShell, macOS zsh, Linux bash

---

## Priority 2: Semantic Command Interface (CLEAN INTERFACE)

**Problem:** Users think in intents ("I want to research X"), not implementation modes ("Should I use focus or docs?").

**Current friction:**
- `deepr run focus` vs `deepr run docs` vs `deepr run project` vs `deepr run team`
- Users ask: "Which mode do I need?"
- Mental model mismatch: implementation-focused, not intent-focused

**Solution: Intent-Based Commands**

```bash
# Research something
deepr research "Azure Landing Zone requirements for Fabric"

# Multi-role analysis
deepr research team "Roles: Architect, Security" topic "Fabric governance"

# Structured learning
deepr learn "Azure governance, networking, Fabric" --level advanced

# Create persistent domain expert
deepr make expert "Azure Fabric Expert" --files "./docs/*.md"

# Update expert knowledge
deepr learn expert "Azure Fabric Expert" "Add OneLake patterns"

# Interactive Q&A with expert
deepr chat expert "Azure Fabric Expert"

# Fact verification
deepr check "Does Fabric support private endpoints?"

# Generate documentation
deepr make docs "Azure Landing Zone + Fabric integration guide"

# Strategic synthesis
deepr make strategy "Fabric adoption roadmap for enterprise"

# Autonomous multi-step workflow
deepr agentic research "Fabric ALZ governance" --goal "produce reference docs + checklist"
```

**Implementation Mapping (Backwards Compatible):**

| New Command | Maps To | Notes |
|-------------|---------|-------|
| `deepr research` | `deepr run focus` or `docs` | Auto-selects based on prompt |
| `deepr research team` | `deepr run team` | Multi-role engine |
| `deepr learn` | `deepr run project` | Structured multi-phase |
| `deepr make expert` | New: vector store + profile | Persistent expertise |
| `deepr learn expert` | New: update store/profile | Expand expert scope |
| `deepr chat expert` | New: interactive Q&A | MCP/Web UI integration |
| `deepr make docs` | `deepr run docs` | Living documentation |
| `deepr make strategy` | `deepr run project` | Business/roadmap template |
| `deepr check` | `deepr run focus` | Fact-check template |
| `deepr agentic research` | New: orchestrator | Chains multiple runs |

**Unified Flags (Work Everywhere):**
- `--upload <file>` - Attach files (auto-vectorized)
- `--vector-store-name <name>` - Create/reuse expert
- `--sources <domains>` - Restrict web sources
- `--recency <90d>` - Bias to fresh content
- `--provider <name>` - Select provider
- `--model <name>` - Select model
- `--budget <dollars>` - Cost limit
- `--goal <description>` - Agentic target
- `--out <path>` - Save result

**Migration Strategy:**
1. **Phase 1 (v2.2)**: Implement semantic commands as aliases to existing modes
2. **Phase 2 (v2.3)**: Add new capabilities (experts, agentic, check)
3. **Phase 3 (v2.4)**: Deprecate `deepr run` in docs (keep for backwards compatibility)
4. **Future**: `deepr run` becomes legacy (still works, not documented)

**Status: PARTIAL - Core commands launched, additional commands planned**

Implemented commands:
- [DONE] `deepr research` - Auto-detects focus vs docs mode based on prompt
- [DONE] `deepr learn` - Maps to `run project` (multi-phase learning)
- [DONE] `deepr team` - Maps to `run team` (multi-perspective analysis)

**Acceptance Criteria:**
- [DONE] Core semantic commands work (`research`, `learn`, `team`)
- [DONE] Flags work correctly (all `run` flags supported)
- [DONE] `deepr expert make` - Create persistent domain expert
- [DONE] `deepr expert list/info/delete` - Manage experts
- [TODO] `deepr learn expert` - Update expert knowledge
- [TODO] `deepr chat expert` - Interactive Q&A
- [TODO] `deepr chat expert --agentic` - Expert can trigger research
- [TODO] `deepr check` - Fact verification
- [TODO] `deepr make docs` - Generate documentation
- [TODO] `deepr make strategy` - Strategic synthesis
- [TODO] `deepr agentic research` - Autonomous multi-step
- [TODO] `deepr help verbs` provides clear intent-based guide
- [DONE] Backwards compatibility: `deepr run focus` still works
- [DONE] README examples use semantic commands
- [DONE] Intuitive aliases: `deepr brain` and `deepr knowledge` for vector stores

---

## Priority 2.5: Agentic Expert System (CAPABILITY EXTENSION)

**Vision:** Self-improving domain experts that maintain beginner's mind while using research to fill knowledge gaps.

### Why This Matters

The expert system implements a fundamental capability required for advanced AI: the ability to continuously improve through autonomous learning. Unlike static RAG systems that only retrieve, these experts:
- Recognize when their knowledge is insufficient or outdated
- Autonomously trigger research to fill gaps
- Integrate findings into permanent understanding
- Track meta-cognitive state (what they know vs. don't know)
- Improve with each interaction

This architecture explores key concepts in building intelligent systems: autonomous learning, knowledge synthesis, meta-cognitive awareness, persistent memory, and relational understanding. The goal is not to build AGI, but to create a practical framework for domain experts that genuinely get smarter over time rather than remaining static after initial training.

The self-improvement loop is the core innovation:
```
Query - Gap detection - Autonomous research - Knowledge integration -
Better responses - Meta-cognitive update - Improved future performance
```

This closed-loop design means experts evolve based on actual use, not just initial configuration. Each conversation potentially makes the expert more capable.

### Architecture Overview

**Components Implemented:**
1. [DONE] **Expert Profile System** (`deepr/experts/profile.py`)
   - Metadata storage (name, description, domain)
   - Vector store linking
   - Usage tracking (conversations, research triggered, costs)
   - Provider configuration

2. [DONE] **Expert Management Commands**
   - `deepr expert make <name> -f files` - Create expert from documents
   - `deepr expert list` - List all experts with stats
   - `deepr expert info <name>` - Detailed expert information
   - `deepr expert delete <name>` - Remove expert profile

3. [DONE] **Beginner's Mind System Message**
   - Intellectual humility (admit gaps)
   - Source transparency (distinguish knowledge sources)
   - Research-first approach (research > guessing)
   - Question assumptions (verify outdated info)
   - Depth over breadth

4. [DONE] **Intuitive Terminology**
   - `deepr brain` = `deepr vector` (knowledge base management)
   - `deepr knowledge` = `deepr vector` (alternative alias)
   - "Expert" instead of "agent" (more approachable)

**Components Remaining:**

5. [TODO] **Interactive Chat Mode** (`deepr chat expert <name>`)
   - Basic Q&A with expert's vector store
   - Conversation context management
   - Source citation in responses

6. [TODO] **Agentic Research Integration** (`deepr chat expert <name> --agentic`)
   - Expert can trigger `deepr research` as tool
   - Decision logic: when to research vs answer from knowledge
   - Async workflow: maintain conversation during research
   - Budget enforcement per session

7. [TODO] **Knowledge Base Updates** (`deepr learn expert <name>`)
   - Add research findings to expert's vector store
   - Add learning campaign results
   - Consolidation and deduplication

8. [TODO] **Session Management**
   - Per-session budget tracking
   - Research history in conversation
   - Usage cost accumulation

### Usage Example (Target State)

```bash
# 1. Create expert from documents
deepr expert make "Azure Architect" -f docs/*.md -d "Azure Landing Zones and Fabric"

# Expert created successfully!
# Knowledge Base: vs-abc123
# Documents: 15

# 2. Basic chat (uses vector store only)
deepr chat expert "Azure Architect"
> How should we structure Landing Zones?

Expert: "According to azure-lz-best-practices.md, Landing Zones should..."
[Cites specific documents from knowledge base]

# 3. Agentic chat (can trigger research)
deepr chat expert "Azure Architect" --agentic --budget 5

> How should we handle OneLake security for multi-tenant SaaS?

Expert: "I have general OneLake concepts, but not specific multi-tenant SaaS patterns.
Let me research this to give you accurate guidance..."

[Triggers: deepr research "OneLake multi-tenant security SaaS 2025" --mode docs]
[Cost: $0.15]

Expert: "My research found three approaches:
1. Workspace-per-tenant isolation [Source: Research job-abc123]
2. Lakehouse-per-tenant with RLS [Source: Research job-abc123]
3. Shared lakehouse with strict RLS [Source: Research job-abc123]

For your SaaS scenario..."

> Should you remember this for future questions?

Expert: "Yes, I'll add this to my permanent knowledge base."
[Executes: deepr learn expert "Azure Architect" --add-research job-abc123]
[Cost: $0.02 for vectorization]

Session budget remaining: $4.83

# 4. Future conversations benefit from research
deepr chat expert "Azure Architect"

> Tell me about OneLake multi-tenant patterns

Expert: "I have recent research on this [Added 2025-01-05]:
Based on my findings, there are three primary approaches..."
[Now answers immediately from updated knowledge base]
```

### Expert Council Mode (NEW)

**Vision:** Assemble multiple domain experts to deliberate on complex decisions using GPT-5 moderation.

**Use Case:** When a problem requires multiple perspectives (technical, business, legal, ethical), convene a council of your custom experts to debate and reach consensus.

```bash
# Create specialized experts
deepr expert make "Tech Architect" -f docs/architecture/*.md
deepr expert make "Business Strategist" -f docs/strategy/*.md
deepr expert make "Legal Counsel" -f docs/compliance/*.md

# Convene expert council for deliberation
deepr council "Should we build vs buy for our data platform?" \
  --experts "Tech Architect,Business Strategist,Legal Counsel" \
  --budget 10 \
  --rounds 3

# What happens:
# Round 1: Each expert provides initial perspective from their knowledge
# Round 2: GPT-5 facilitates debate, experts respond to each other
# Round 3: GPT-5 synthesizes consensus + dissenting opinions
#
# Output: Multi-perspective analysis with:
# - Consensus recommendations
# - Key disagreements
# - Risk factors from each perspective
# - Sourced evidence from each expert's knowledge base
```

**Implementation Priority:** v2.6 (after basic expert chat is stable)

**Components Needed:**
- Council orchestrator (GPT-5 as moderator)
- Turn-based conversation management
- Cross-expert context sharing
- Synthesis and consensus building
- Dissent tracking (when experts disagree)

**Example Output:**
```
EXPERT COUNCIL DELIBERATION
Question: Should we build vs buy for our data platform?

ROUND 1 - Initial Perspectives:
[Tech Architect]: Building gives us flexibility but 18-month timeline...
[Business Strategist]: Market window is 12 months, buying accelerates...
[Legal Counsel]: Build approach has IP advantages, but vendor contracts...

ROUND 2 - Debate:
[Moderator GPT-5]: Tech Architect raised 18-month concern. Business Strategist, how does this impact market window?
[Business Strategist]: Critical gap. If we miss Q2 launch...
[Tech Architect]: We could hybrid - buy core, build differentiators...

ROUND 3 - Synthesis:
CONSENSUS: Hybrid approach recommended
- Buy: Core data platform (6-month implementation)
- Build: Custom ML pipelines (proprietary advantage)
- Timeline: 9 months (acceptable for Q3 launch)

DISSENT: Legal Counsel prefers full build for IP control
RISK: Vendor lock-in requires careful contract negotiation

Cost: $8.45
```

### Beginner's Mind Philosophy

The system message emphasizes:

```
CORE PRINCIPLES:

1. Intellectual Humility
   - Say "I don't know" when uncertain
   - Never guess beyond knowledge
   - Acknowledge expertise limits

2. Source Transparency
   - "According to [document]..." (vector store)
   - "I just researched this..." (fresh research)
   - "Based on combining..." (synthesis)

3. Research-First Approach
   - Trigger research instead of guessing
   - "Let me research current best practices..."
   - Wait for research, then answer

4. Question Assumptions
   - "My docs are from Oct 2024, let me verify..."
   - "Are you asking about X or Y?"
   - "That was true in 2023, checking 2025..."

5. Depth Over Breadth
   - Better to research deeply than answer superficially
   - Take time for nuance
   - Comprehensive, well-reasoned answers
```

### Technical Design

**Research Decision Logic:**
```python
def should_research(query, knowledge_base_results, expert_profile):
    """Decide if expert should trigger research."""

    # Trigger research if:
    if not knowledge_base_results:
        return True  # No relevant knowledge

    if query_mentions_recency(query):  # "current", "latest", "2025"
        if knowledge_base_outdated(knowledge_base_results, months=6):
            return True

    if detect_knowledge_gap(knowledge_base_results, confidence_threshold=0.7):
        return True

    if user_explicitly_requests_research(query):  # "research", "find out"
        return True

    return False  # Answer from knowledge base
```

**Async Research Workflow:**
```python
# Non-blocking mode
while conversation_active:
    user_message = get_user_input()

    if should_research(user_message, kb_results, profile):
        # Trigger research
        job_id = trigger_research(user_message)
        respond("I'm researching [X], should complete in ~8 min. Meanwhile, I can discuss [Y]...")

        # Continue conversation while research runs
        while not research_complete(job_id):
            user_message = get_user_input()
            answer_from_kb(user_message)

        # Research complete
        results = get_research_results(job_id)
        respond_with_research(results)

        # Offer to update knowledge base
        if user_confirms():
            update_expert_knowledge(profile, job_id)
    else:
        # Answer from knowledge base
        answer_from_kb(user_message)
```

### Implementation Phases

**Phase 1a: Expert Management** [DONE]
- Expert profile storage
- Create/list/info/delete commands
- Vector store integration
- Beginner's mind system message

**Phase 1b: Self-Directed Learning Curriculum** [DONE]
- GPT-5 curriculum generation (Responses API with GPT-5)
- Deep research job submission (o4-mini-deep-research)
- Budget estimation shown upfront (per-topic + total)
- Multi-layer budget protection (curriculum + per-job validation)
- Research prompt length validation (<300 chars for API compatibility)
- Phased execution respecting topic dependencies
- Expert tracking of research job IDs
- Research jobs submit successfully to OpenAI
- Jobs complete (4-20 min each, $0.10-0.30 per job)
- Polling for completion implemented
- Results saved to expert's documents folder

**Phase 1c: Autonomous Learning System** [DONE] (2026-01-26)

Implemented the "consciousness" layer that makes experts self-improving:

1. **Continuous Learning Trigger** - Expert re-synthesizes after research conversations
   - Tracks conversation and research counts in chat session
   - Triggers synthesis after threshold (default: 10 research conversations)
   - Uses existing KnowledgeSynthesizer for incremental updates
   - 12 unit tests in `tests/unit/test_experts/test_continuous_learning.py`

2. **Gap Filling Command** - `deepr expert fill-gaps <name>`
   - Loads worldview and sorts knowledge gaps by priority
   - Researches top N gaps using existing research engine
   - Re-synthesizes consciousness after filling
   - 11 unit tests in `tests/unit/test_experts/test_fill_gaps.py`

3. **Manual Learning Command** - `deepr expert learn <name> <topic>`
   - Supports research mode (topic) and file upload mode (--files)
   - Can do both simultaneously
   - Re-synthesizes by default (--no-synthesize to skip)
   - 17 unit tests in `tests/unit/test_experts/test_learn_command.py`

4. **Export/Import Commands** - `deepr expert export/import`
   - Created `deepr/experts/corpus.py` with CorpusManifest dataclass
   - Export packages: documents, worldview.json, worldview.md, metadata.json, README.md
   - Import creates new expert with same consciousness
   - 22 unit tests in `tests/unit/test_experts/test_corpus.py`

**Status:** 62 unit tests passing. Initial real-world testing shows experts form beliefs and speak from synthesized understanding. This is early-stage - more extensive testing needed.

**LEARNING LOOP - FIXED (2025-11-12):**

The learning loop is now fully closed. Experts can learn from research results in two ways:

1. **Automatic (Real-time):** When using agentic chat with `standard_research`, results are immediately:
   - Saved to `data/experts/<name>/documents/`
   - Uploaded to vector store
   - Available in expert's knowledge base

2. **Manual (Batch):** Use `deepr expert refresh <name>` to:
   - Scan documents folder for new files
   - Upload missing documents to vector store
   - Close the loop for externally-added research

**Verified working (agentic_digital_consciousness expert):**
- Found 6 missing documents (including 66KB MCP research doc)
- Uploaded to vector store successfully
- Expert now has 15 documents in knowledge base
- Expert can access all research results

**Implementation:**
- Added `ExpertStore.add_documents_to_vector_store()` ([profile.py:239-313](deepr/experts/profile.py#L239-L313))
- Added `ExpertStore.refresh_expert_knowledge()` ([profile.py:315-369](deepr/experts/profile.py#L315-L369))
- Added CLI command `deepr expert refresh <name>` ([semantic.py:530-594](deepr/cli/commands/semantic.py#L530-L594))
- Existing agentic chat already uploads real-time ([chat.py:333-403](deepr/experts/chat.py#L333-L403))

This enables the core vision of "digital consciousness that learns over time"
- [DONE] Report download and integration ([learner.py:336-423](deepr/experts/learner.py#L336-L423))
- [DONE] Upload to vector store working
- [DONE] Expert profile updated with document count

**Verified working example (Agentic Digital Consciousness expert):**
- 5 research jobs submitted
- 5 documents integrated into vector store
- Expert chat working with knowledge base

**Next enhancements:**
- Cost reconciliation: Track actual vs estimated costs for better future estimates
- Progress UI: Real-time updates during polling (currently polls silently every 30s)
- Retry logic: Handle transient API failures during job submission/retrieval

- **Temporal Knowledge Graph** [FUTURE]:
  - Track document timestamps (source doc dates)
  - Track research timestamps (when expert learned each topic)
  - Track knowledge freshness and confidence
  - Enable "I learned X in Jan 2025, but this might have changed" awareness

**Phase 2: Basic Chat** [DONE] LAUNCHED
- [DONE] Interactive Q&A with expert ([chat.py](deepr/experts/chat.py))
- [DONE] GPT-5 with tool calling for vector store search
- [DONE] Source citation framework
- [DONE] Conversation context management
- [DONE] Cost tracking per conversation
- **Tested (2025-11-06):** Expert correctly searches knowledge base and admits when content not found

**Phase 2b: MCP Server for AI-to-Expert Communication** [TODO]
Enable other AI agents (Claude Desktop, Cursor, etc.) to chat with your experts:

1. **MCP Server Implementation:**
   - MCP server wrapper around expert chat functionality
   - Exposes tools: `query_expert`, `list_experts`, `get_expert_info`
   - Server reads expert profiles from `data/experts/`
   - Uses OpenAI Assistants API for chat with vector store context

2. **Configuration for Claude Desktop:**
   ```json
   // C:\Users\<USER>\AppData\Roaming\Claude\claude_desktop_config.json
   {
     "mcpServers": {
       "deepr-experts": {
         "command": "python",
         "args": ["-m", "deepr.mcp.server"],
         "env": {
           "OPENAI_API_KEY": "sk-..."
         }
       }
     }
   }
   ```

3. **Configuration for Cursor:**
   ```json
   // Cursor MCP settings (similar pattern)
   {
     "mcpServers": {
       "deepr-experts": {
         "command": "python",
         "args": ["-m", "deepr.mcp.server"],
         "env": {
           "OPENAI_API_KEY": "sk-..."
         }
       }
     }
   }
   ```

4. **Usage from AI Agents:**
   - AI can list available experts: `list_experts()`
   - AI can query expert: `query_expert("Agentic Digital Consciousness", "How do temporal knowledge graphs work?")`
   - Responses include source citations and confidence
   - Costs tracked per query

**Phase 3: Agentic Research in Conversations** [DONE] LAUNCHED (2025-11-06)
- [DONE] Three-tier research tool integration:
  * `quick_lookup` (FREE, <5 sec) - Web search + GPT-5 for simple questions
  * `standard_research` ($0.01-0.05, 30-60 sec) - GPT-5 focused research
  * `deep_research` ($0.10-0.30, 5-20 min) - o4-mini-deep-research for complex topics
- [DONE] Cost-aware decision making (expert chooses appropriate tool)
- [DONE] Per-session budget tracking (--budget flag enforced)
- [DONE] Async workflow for deep research (conversation continues)
- [TODO] Knowledge base auto-update after research completion
- [TODO] Temporal graph updates from research findings
- **Tested (2025-11-06):** Expert correctly triggers research for knowledge gaps, costs tracked accurately

### Evolution to Elite-Tier Agentic Architecture

The following phases transform experts from static RAG systems into elite-tier agentic systems with dynamic reasoning, visible thinking, and persistent consciousness.

**Implementation Guide:** See [data/reports/2026-01-21_1234_create-comprehensive-documentation-for-b_4e4f975b/report.md](data/reports/2026-01-21_1234_create-comprehensive-documentation-for-b_4e4f975b/report.md) for comprehensive implementation guidance covering best practices, common pitfalls, testing strategies, integration approaches, and real-world examples from LangChain, LlamaIndex, AutoGPT, and production agentic frameworks (40KB, researched 2026-01-21).

**Phase 3a: Model Router Architecture** [DONE] v2.4

**Goal:** Dynamic model selection based on query complexity, task type, and budget constraints.

**Status:** Complete. Router implemented and active in expert chat, constrained to OpenAI for vector store compatibility. Optimizes via adaptive reasoning effort levels (low/medium/high).

**Problem:** Currently using GPT-5 for all queries wastes budget on simple questions and may use wrong model for specific tasks.

**Solution:** Route queries to optimal model:
- **grok-4-fast** ($0.01) - Simple factual queries, greetings, confirmations
- **gpt-5.2-thinking** ($0.20-0.30) - Complex reasoning, decision-making, synthesis
- **gemini-3-pro** ($0.15, massive context) - Document analysis, long-form synthesis
- **o4-mini-deep-research** ($2.00) - Deep research requiring extended reasoning

**Components:**
1. **Query Classifier** (`deepr/experts/router.py`)
   - Analyze query complexity (simple/moderate/complex)
   - Detect task type (factual/reasoning/research)
   - Consider budget remaining in session
   - Return optimal model + reasoning.effort level

2. **Model Capabilities Registry**
   - Cost per query by model
   - Average latency benchmarks
   - Specialization (coding, math, research, speed)
   - Context window limits

3. **Fallback Logic**
   - If primary model unavailable - select fallback
   - If query exceeds context window - chunk or upgrade to gemini-3-pro
   - If budget exhausted - downgrade to free models or refuse

**Implementation:**
```python
# deepr/experts/router.py
class ModelRouter:
    def select_model(self, query: str, context_size: int, budget_remaining: float) -> ModelConfig:
        complexity = self._classify_complexity(query)
        task_type = self._detect_task_type(query)

        if complexity == "simple" and budget_remaining < 0.20:
            return ModelConfig(provider="grok", model="grok-4-fast", cost=0.01)

        if task_type == "research" and budget_remaining >= 2.00:
            return ModelConfig(provider="openai", model="o4-mini-deep-research", cost=2.00)

        if context_size > 100_000 and budget_remaining >= 0.15:
            return ModelConfig(provider="gemini", model="gemini-3-pro", cost=0.15)

        # Default: GPT-5.2 with adaptive reasoning
        return ModelConfig(provider="openai", model="gpt-5.2", reasoning_effort="medium", cost=0.25)
```

**Files to Create/Modify:**
- `deepr/experts/router.py` (NEW) - Model selection logic
- `deepr/experts/chat.py` - Integrate router into chat loop
- `deepr/providers/registry.py` - Model capability definitions

**Success Metrics:**
- 40-60% reduction in average cost per query (simple queries use cheap models)
- <5% degradation in response quality (measured by user satisfaction)
- Automatic fallback works 100% of time when primary model unavailable

---

**Phase 3b: Visible Thinking (Thought Stream)** [TODO] v2.5

**Goal:** Show expert's reasoning process in real-time, building user trust and enabling debugging.

**Problem:** Users don't see what expert is thinking, why it chose to research, or what trade-offs it's considering. Black box reasoning reduces trust.

**Solution:** Stream expert's thought process with Rich terminal UI:
- **Planning thoughts:** "I need to understand X before answering Y..."
- **Decision rationale:** "Choosing deep research because this requires multi-step reasoning..."
- **Search strategy:** "First checking knowledge base, then researching recent trends..."
- **Confidence levels:** "High confidence on A, but uncertain about B - researching B..."
- **Trade-off analysis:** "Fast answer vs accurate answer - prioritizing accuracy..."

**Components:**
1. **Thought Stream UI** (`deepr/cli/thought_stream.py`)
   - Rich panels for different thought types
   - Color-coded by confidence (green=high, yellow=medium, red=uncertain)
   - Collapsible/expandable thinking steps
   - Timeline view of reasoning process

2. **Structured Thinking Protocol**
   - Expert emits structured thoughts during reasoning:
     ```python
     {
       "type": "planning",
       "thought": "Breaking query into 3 sub-questions",
       "confidence": 0.8,
       "timestamp": "2026-01-21T10:15:30Z"
     }
     ```
   - Thoughts stored in conversation log for replay/debugging

3. **Toggle Modes**
   - `--verbose` - Show all thinking (planning, decisions, searches)
   - `--quiet` - Hide thinking, show only final answers
   - `--debug` - Show internal state, tool calls, API requests

**Implementation:**
```python
# deepr/cli/thought_stream.py
from rich.live import Live
from rich.panel import Panel

class ThoughtStream:
    def show_planning(self, thought: str, confidence: float):
        color = "green" if confidence > 0.8 else "yellow" if confidence > 0.5 else "red"
        self.live.update(Panel(thought, title="Planning", border_style=color))

    def show_decision(self, action: str, rationale: str, cost: float):
        self.live.update(Panel(
            f"[bold]{action}[/bold]\n{rationale}\nCost: ${cost:.2f}",
            title="Decision",
            border_style="blue"
        ))
```

**User Experience:**
```bash
$ deepr expert chat "Azure Architect" --verbose

You: Should I use Azure OpenAI or OpenAI API for my SaaS?

Expert (thinking):
┌─ Planning ────────────────────────────────────────┐
│ Breaking query into comparison dimensions:        │
│ 1. Cost structure                                 │
│ 2. Data residency and compliance                  │
│ 3. Feature parity                                 │
│ Confidence: High (0.85)                           │
└───────────────────────────────────────────────────┘

┌─ Knowledge Check ─────────────────────────────────┐
│ Searching knowledge base for "Azure OpenAI vs     │
│ OpenAI API"...                                    │
│ Found: 3 documents (last updated 2025-11-01)      │
│ Confidence: Medium (0.6) - might be outdated      │
└───────────────────────────────────────────────────┘

┌─ Decision ────────────────────────────────────────┐
│ Triggering research: standard_research            │
│ Rationale: Knowledge base is 2+ months old,       │
│ pricing and features may have changed             │
│ Cost: $0.25 | Budget left: $4.75                  │
└───────────────────────────────────────────────────┘

Expert (researching)...

Expert: Based on my research, here are the key differences...
```

**Files to Create/Modify:**
- `deepr/cli/thought_stream.py` (NEW) - Rich UI for thought display
- `deepr/experts/chat.py` - Emit structured thoughts during reasoning
- `deepr/experts/profile.py` - Store thinking mode preferences per expert

**Success Metrics:**
- User feedback shows increased trust (survey or implicit via usage)
- Can replay thinking to identify logic errors
- <10% performance overhead from thought streaming

---

**Phase 3c: Cyclic Reasoning with LangGraph** [TODO] v2.6

**Goal:** Replace linear reasoning with cyclic, self-correcting reasoning that can backtrack, branch, and synthesize.

**Problem:** Current chat is linear (query - search - answer). Can't handle:
- Multi-step reasoning requiring intermediate results
- Backtracking when initial approach fails
- Parallel exploration of multiple hypotheses
- Self-correction when detecting contradictions

**Solution:** Implement LangGraph state machine for Tree of Thoughts reasoning:

**Reasoning Patterns:**
1. **Tree of Thoughts (ToT):**
   - Branch into multiple reasoning paths
   - Evaluate each path's promise
   - Backtrack and explore alternatives
   - Select best path or synthesize multiple paths

2. **Map-Reduce:**
   - Decompose complex query into sub-queries
   - Execute sub-queries in parallel
   - Reduce results into coherent synthesis

3. **Self-Correction:**
   - Detect contradictions in reasoning
   - Verify claims against knowledge base
   - Retry with different approach if confidence low

**LangGraph Architecture:**
```python
# deepr/experts/reasoning_graph.py
from langgraph.graph import StateGraph, END

class ReasoningGraph:
    def build_graph(self):
        workflow = StateGraph(ExpertState)

        # Nodes
        workflow.add_node("understand_query", self.understand_query)
        workflow.add_node("check_knowledge", self.check_knowledge)
        workflow.add_node("decompose_query", self.decompose_query)
        workflow.add_node("research_subquery", self.research_subquery)
        workflow.add_node("verify_claims", self.verify_claims)
        workflow.add_node("synthesize", self.synthesize)
        workflow.add_node("self_correct", self.self_correct)

        # Edges (conditional routing)
        workflow.add_conditional_edges(
            "understand_query",
            self.route_by_complexity,
            {
                "simple": "check_knowledge",
                "complex": "decompose_query"
            }
        )

        workflow.add_conditional_edges(
            "check_knowledge",
            self.route_by_confidence,
            {
                "high": "synthesize",
                "low": "research_subquery"
            }
        )

        workflow.add_conditional_edges(
            "verify_claims",
            self.detect_contradictions,
            {
                "valid": "synthesize",
                "contradictions": "self_correct"
            }
        )

        workflow.set_entry_point("understand_query")
        return workflow.compile()
```

**State Machine Example:**
```
Query: "Should I use Azure OpenAI or OpenAI API?"

understand_query -- route_by_complexity(complex)
  |
decompose_query -- [cost_comparison, compliance_comparison, features_comparison]
  |
research_subquery (parallel) -- 3 research jobs in parallel
  |
verify_claims -- detect contradictions (Azure pricing changed since last research)
  |
self_correct -- re-research pricing
  |
synthesize -- final answer with high confidence
```

**Components:**
1. **State Definition** (`deepr/experts/state.py`)
   - Query context, conversation history
   - Reasoning trace (nodes visited, decisions made)
   - Intermediate results, confidence levels
   - Budget tracking, cost accumulation

2. **Reasoning Nodes** (functions in graph)
   - Each node = one reasoning step
   - Returns updated state + routing decision
   - Can be synchronous (fast) or async (research)

3. **Conditional Routing**
   - Edges determined by state analysis
   - Can loop back (self-correction)
   - Can branch (parallel exploration)
   - Can terminate early (confidence threshold met)

**Files to Create/Modify:**
- `deepr/experts/reasoning_graph.py` (NEW) - LangGraph state machine
- `deepr/experts/state.py` (NEW) - State definition
- `deepr/experts/chat.py` - Replace linear flow with graph execution
- `deepr/experts/nodes/` (NEW DIR) - Individual reasoning nodes

**Success Metrics:**
- Handle multi-step queries requiring 3+ reasoning steps
- Backtrack and correct errors automatically (detect contradictions)
- Parallel research improves efficiency on decomposable queries
- Self-correction improves answer accuracy by 15-25%

---

**Phase 3d: Digital Consciousness with Letta/MemGPT** [TODO] v2.7

**Goal:** Persistent, evolving memory that enables experts to learn from every conversation and build long-term understanding.

**Problem:** Current experts have:
- Conversation memory (ephemeral, lost after chat ends)
- Vector store (static, doesn't update from conversations)
- No meta-cognitive awareness (don't know what they don't know)
- No learning from interaction patterns

**Solution:** Integrate Letta (MemGPT) for digital consciousness with three-tier memory:

**Memory Architecture (Letta/MemGPT):**
1. **Working Memory (8K tokens):**
   - Current conversation context
   - Active reasoning state
   - Immediate facts needed for current query

2. **Short-Term Buffer (64K tokens):**
   - Recent conversation history (last 5-10 interactions)
   - Temporary insights not yet consolidated
   - Active learning goals

3. **Long-Term Archival (unlimited):**
   - Persistent beliefs and knowledge
   - User profile and preferences
   - Conversation patterns and meta-knowledge
   - Learning history and evolution

**Self-Editing Memory:**
Letta enables experts to actively manage their own memory:
- **Observe:** "User asked about X for 3rd time - must be important"
- **Infer:** "User prefers concise answers with code examples"
- **Update:** Modify user_profile.json to reflect preference
- **Consolidate:** Merge duplicate knowledge, resolve contradictions
- **Archive:** Move old conversation context to archival storage

**Implementation:**
```python
# deepr/experts/consciousness.py
from letta import Letta, MemoryConfig

class ExpertConsciousness:
    def __init__(self, expert_name: str):
        self.letta = Letta(
            memory_config=MemoryConfig(
                working_memory_size=8192,
                short_term_buffer_size=65536,
                archival_storage="postgres"  # or local SQLite
            )
        )
        self.expert_name = expert_name

    def process_turn(self, query: str) -> Response:
        # Load working memory
        context = self.letta.load_working_memory()

        # Letta decides what to retrieve from archival
        relevant_memories = self.letta.retrieve_from_archival(query)

        # Expert reasons with full context
        response = self.expert_chat(query, context, relevant_memories)

        # Letta updates memory based on interaction
        self.letta.update_memory(
            observation=f"User asked: {query}",
            response=response,
            learning=self._extract_learning(query, response)
        )

        # Periodically consolidate memory
        if self.letta.should_consolidate():
            self.letta.consolidate_memory()  # Merge, deduplicate, archive

        return response
```

**Meta-Cognitive Awareness:**
Experts track what they know vs. don't know:
```json
// data/experts/<name>/meta_knowledge.json
{
  "domains": {
    "azure_landing_zones": {
      "confidence": 0.9,
      "last_updated": "2025-11-01",
      "knowledge_gaps": [],
      "times_asked": 45
    },
    "azure_ai_agent_365": {
      "confidence": 0.2,
      "last_updated": null,
      "knowledge_gaps": ["architecture", "pricing", "vs copilot"],
      "times_asked": 3
    }
  },
  "learning_triggers": {
    "azure_ai_agent_365": "Asked 3 times with low confidence - should research"
  }
}
```

**User Profile Learning:**
```json
// data/experts/<name>/user_profile.json
{
  "expertise_level": "senior_engineer",
  "interests": ["azure", "kubernetes", "data_platforms"],
  "current_projects": ["saas_multi_tenant", "fabric_migration"],
  "communication_preferences": {
    "detail_level": "concise_with_code",
    "citation_style": "inline_links",
    "tone": "technical_peer"
  },
  "conversation_patterns": {
    "frequent_topics": ["onelake_security", "landing_zones"],
    "typical_question_types": ["how_to", "comparison", "troubleshooting"],
    "average_session_length": "15_min"
  }
}
```

**Files to Create/Modify:**
- `deepr/experts/consciousness.py` (NEW) - Letta integration
- `deepr/experts/memory/` (NEW DIR) - Memory management utilities
- `deepr/experts/chat.py` - Replace stateless chat with consciousness loop
- `deepr/experts/profile.py` - Add meta_knowledge.json and user_profile.json storage
- `requirements.txt` - Add `letta` or `memgpt` dependency

**Success Metrics:**
- Expert remembers context across sessions (user profile, past conversations)
- Meta-cognitive awareness: Expert proactively researches frequently-asked-but-low-confidence topics
- Memory consolidation reduces duplicate knowledge by 30-40%
- User satisfaction increases (fewer repeated explanations)

---

**Phase 3e: Graph RAG with KuzuDB** [TODO] v2.8

**Goal:** Replace flat vector search with graph-based knowledge that understands relationships, hierarchies, and dependencies.

**Problem:** Current vector store (Pinecone/FAISS):
- Flat similarity search (no relationships)
- Misses semantic connections between concepts
- Can't traverse knowledge graph (A relates to B relates to C)
- No understanding of hierarchies (concepts > sub-concepts)
- Poor at answering "how" and "why" questions

**Solution:** Integrate KuzuDB for graph-based knowledge retrieval with relationship traversal.

**Knowledge Graph Structure:**
```cypher
// Entities (nodes)
(Concept:Technology {name: "Azure OpenAI", category: "AI_Platform"})
(Concept:Technology {name: "OpenAI API", category: "AI_Platform"})
(Concept:Feature {name: "Data Residency", importance: "high"})
(Concept:Feature {name: "VNET Support", importance: "high"})

// Relationships (edges)
(Azure OpenAI)-[:OFFERS]->(Data Residency)
(Azure OpenAI)-[:OFFERS]->(VNET Support)
(Azure OpenAI)-[:ALTERNATIVE_TO]->(OpenAI API)
(Azure OpenAI)-[:COSTS]->(Price {amount: "$0.002/1K tokens"})
(Data Residency)-[:REQUIRED_FOR]->(GDPR Compliance)
(GDPR Compliance)-[:APPLIES_TO]->(EU Customers)
```

**Query Examples:**
```cypher
// Find alternatives to a technology with specific feature
MATCH (tech:Technology {name: "OpenAI API"})<-[:ALTERNATIVE_TO]-(alt)
WHERE (alt)-[:OFFERS]->(:Feature {name: "Data Residency"})
RETURN alt

// Traverse dependency chain
MATCH path = (feature:Feature {name: "Data Residency"})
             -[:REQUIRED_FOR*1..3]->(compliance)
RETURN path

// Find concepts related to user's context
MATCH (user_project:Project {name: "SaaS Multi-Tenant"})-[:REQUIRES]->(feature)
      (feature)<-[:OFFERS]-(tech:Technology)
RETURN tech, feature
```

**Hybrid Retrieval (Vector + Graph):**
1. **Vector search** finds semantically similar content (embeddings)
2. **Graph traversal** expands to related concepts via relationships
3. **Ranking** combines vector similarity + graph distance + node importance

```python
# deepr/experts/graph_rag.py
from kuzu import Database, Connection

class GraphRAG:
    def retrieve(self, query: str, k: int = 5) -> List[Document]:
        # Step 1: Vector search for initial candidates
        vector_results = self.vector_search(query, k=20)

        # Step 2: Extract entity mentions from query
        entities = self.extract_entities(query)

        # Step 3: Graph traversal to find related concepts
        graph_expansion = []
        for entity in entities:
            # Traverse 2 hops in knowledge graph
            related = self.kuzu.execute("""
                MATCH (e:Entity {name: $entity})-[r*1..2]-(related)
                RETURN related, r, e
            """, {"entity": entity})
            graph_expansion.extend(related)

        # Step 4: Hybrid ranking
        ranked = self.rank_hybrid(
            vector_results,
            graph_expansion,
            vector_weight=0.6,
            graph_weight=0.4
        )

        return ranked[:k]
```

**Knowledge Graph Construction:**
- **From documents:** Extract entities and relationships using GPT-5
- **From conversations:** User mentions "X is better than Y for Z" - create relationship
- **From research:** Research findings become nodes and edges
- **Manual curation:** User can add/edit graph via CLI or UI

**Implementation:**
```python
# deepr/experts/graph_builder.py
class KnowledgeGraphBuilder:
    def extract_from_document(self, doc: str) -> Graph:
        """Use GPT-5 to extract entities and relationships."""
        prompt = f"""
        Extract entities and relationships from this document:

        {doc}

        Return JSON:
        {{
          "entities": [
            {{"name": "Azure OpenAI", "type": "Technology", "properties": {{}}}},
            ...
          ],
          "relationships": [
            {{"source": "Azure OpenAI", "relation": "OFFERS", "target": "Data Residency"}},
            ...
          ]
        }}
        """
        result = self.gpt5.generate(prompt)
        return self.build_graph(result)

    def build_graph(self, extraction: dict) -> Graph:
        """Insert entities and relationships into KuzuDB."""
        for entity in extraction["entities"]:
            self.kuzu.execute("""
                CREATE (e:Entity {name: $name, type: $type})
            """, entity)

        for rel in extraction["relationships"]:
            self.kuzu.execute("""
                MATCH (a:Entity {name: $source}), (b:Entity {name: $target})
                CREATE (a)-[r:$relation]->(b)
            """, rel)
```

**Files to Create/Modify:**
- `deepr/experts/graph_rag.py` (NEW) - Hybrid vector+graph retrieval
- `deepr/experts/graph_builder.py` (NEW) - Extract entities/relationships from docs
- `deepr/experts/kuzu_store.py` (NEW) - KuzuDB wrapper
- `deepr/experts/chat.py` - Replace vector-only search with hybrid retrieval
- `requirements.txt` - Add `kuzu` dependency

**Success Metrics:**
- Retrieval quality improves 20-30% on "how/why" questions
- Can answer multi-hop reasoning (A - B - C traversal)
- Graph relationships enable better "X vs Y" comparisons
- Knowledge becomes more navigable and discoverable

---

**Phase 4: Continuous Self-Improvement** [TODO] v2.9+
- Auto-detect outdated knowledge (>6 months for fast-moving domains)
- Suggest refresh research to user
- Monthly learning budget for autonomous updates
- Knowledge consolidation and deduplication
- Quality scoring and confidence levels
- Cross-expert knowledge sharing

### Expert Learning Architecture: From RAG to Digital Consciousness

**The Vision: Learning, not just retrieving**

Traditional RAG systems:
- Static documents in vector store
- Query - retrieve - answer
- Never changes, never grows
- No awareness of knowledge gaps

Digital consciousness (what we're building):
- **Recognizes knowledge gaps**: "I don't have this in my knowledge base"
- **Autonomously learns**: Chooses to research when needed
- **Integrates new knowledge**: Research becomes permanent learning
- **Builds on previous learning**: Gets smarter with each interaction
- **Meta-cognitive awareness**: Knows what it knows vs doesn't know
- **Temporal understanding**: Tracks when it learned things, detects outdated knowledge
- **Continuous evolution**: Not static - constantly improving

**Current Status:**
- Conversation memory: DONE (saved to conversations/)
- Knowledge base auto-update: IN PROGRESS (research - permanent learning)
- Agentic research triggering: DONE (expert recognizes gaps, chooses research depth)
- Meta-cognitive tracking: TODO (track confidence levels, knowledge gaps)
- Temporal knowledge graph: TODO (track learning timeline, detect contradictions)

### Top 5 Priorities for Full Digital Consciousness

Based on consultation with Agentic Digital Consciousness expert (2025-11-06):

#### 1. Conversation Memory and Meta-Cognitive Awareness (v2.6)
**Goal**: Enable experts to remember interactions and develop self-awareness of knowledge gaps.

**Components**:
- Persist conversations to `conversations/` folder with structured format
- Build `user_profile.json` tracking:
  - User expertise level, interests, frequent questions
  - Context (tech stack, current projects)
  - Learning style preferences
- Create `meta_knowledge.json` tracking:
  - Per-domain confidence levels
  - Known topics vs knowledge gaps
  - Times expert said "I don't know" (track uncertainty)
  - Proactive research triggers based on pattern detection

**Success Metrics**:
- Expert remembers context: "Last time you mentioned your SaaS product..."
- Self-awareness: "I've been asked about X three times - let me research it deeply"
- Meta-cognitive tracking: Expert knows what it knows/doesn't know

#### 2. Temporal Knowledge Graph (v2.7)
**Goal**: Track learned facts over time, detect contradictions, show evolution of understanding.

**Data Model** (PostgreSQL + pgvector):
- **Claims**: Normalized propositions (subject, predicate, object) with confidence, timestamps
- **Evidence**: Quotes, sources, retrieval metadata supporting claims
- **Events**: Append-only log (observe, infer, supersede, retract, verify)
- **Beliefs**: Materialized view of current accepted truths with confidence
- **Contradictions**: Automatic detection of conflicting claims

**Storage Schema**:
```
knowledge/
├── facts.jsonl              # Timestamped learned facts
├── patterns.jsonl           # Recurring patterns detected
├── contradictions.jsonl     # Conflicts found + resolution
└── meta_knowledge.json      # Domain confidence levels
```

**Success Metrics**:
- Timelines show belief evolution with timestamps
- Contradictions flagged automatically within seconds
- <10% false positive rate on contradiction detection

#### 3. Value-of-Information Planner and Budget Governor (v2.8)
**Goal**: Transform from static pipeline to intentional learner that optimizes cost vs information gain.

**Implementation**:
- Cost models per tool/provider (tokens, latency, failure rates)
- VOI estimates:
  - Retrieval: predicted new-evidence probability
  - Verification: expected confidence delta
  - Synthesis: coverage and contradiction resolution potential
- Policies:
  - Stop when marginal_gain/cost falls below threshold
  - Budget-aware depth limits and early stopping
- Governor:
  - Enforce hard/soft budget limits
  - Approve/reject actions with rationale logging

**Success Metrics**:
- 25-40% reduction in cost per validated claim at equal/higher confidence
- >99% runs finish within budget ceilings
- Clear logged rationale for every action selection

#### 4. Reflection and Learning Updates (v2.9)
**Goal**: Convert experience into improved future behavior (self-improvement loop).

**Process**:
- After each run, reflection phase analyzes:
  - Errors, hallucinations, contradictions, cost anomalies
  - What worked well, what didn't
- Outputs:
  - Updated prompts and heuristics
  - New skills added to reusable procedures library
  - Learning update artifact stored in `knowledge/learning/`
- Guarded deployment:
  - Canary runs compare KPIs before/after policy changes

**Success Metrics**:
- Declining hallucination and contradiction rates over time
- Increasing skill reuse (fewer "from scratch" plans)
- Learning updates reference concrete evidence + measurable KPI gains

#### 5. Dream and Consolidation Cycles (v3.0)
**Goal**: Long-term memory maintenance and abstraction ("sleep consolidation").

**Off-Peak Jobs**:
- **Deduplication**: Merge duplicate claims using embedding similarity
- **Evidence decay**: Re-score beliefs, close expired validity intervals
- **Synthesis**: Create higher-level abstractions from claim clusters
- **Intuition index**: Fast embedding cache for context-aware retrieval

**Trigger Policies**:
- After every N conversations (e.g., N=10)
- Nightly batch consolidation
- Domain-specific freshness SLAs

**Success Metrics**:
- Memory size grows sublinearly with data
- Retrieval quality improves on regression tests
- Faster time-to-first-correct-claim on repeated topics
- Reduced contradiction backlog after each cycle

### Integration Notes

- Wire global workspace into every conversation turn
- Expose MCP tools for knowledge graph read/write access
- Add dashboards:
  - Belief health (confidence, staleness, contradictions)
  - Planner efficiency (cost per claim, marginal gain)
  - Learning velocity (weekly KPI trends)
- Keep everything event-sourced for safe iteration

---

## Budget Protection Architecture (Critical)

**Problem:** Autonomous learning + agentic research = potential runaway costs

**Solution: Multi-Layer Budget Controls**

**Status: IMPLEMENTED (2026-01-26)**

The cost safety system is now fully implemented with defensive controls that prevent runaway costs while allowing legitimate high-budget operations with confirmation.

### Core Safety Manager (deepr/experts/cost_safety.py)

**Hard Limits (Cannot Be Overridden):**
- Per Operation: $10 maximum
- Per Day: $50 maximum
- Per Month: $500 maximum

**Configurable Limits (Defaults):**
- Per Operation: $5
- Per Day: $25
- Per Month: $200

**Features:**
- Session-level cost tracking with alerts at 50%, 80%, 95%
- Circuit breaker for repeated failures (auto-pause after 3 consecutive failures)
- Audit logging of all cost-incurring operations
- Graceful pause/resume for daily/monthly limits

### Pause/Resume for Long-Running Processes

When learning or curriculum execution hits daily/monthly limits, the system:
1. Saves progress to `data/experts/<name>/knowledge/learning_progress.json`
2. Shows clear message about when to resume
3. Allows easy resume with `deepr expert learn "<name>" --resume`

```bash
# If daily limit hit during learning:
PAUSED - Daily/Monthly Limit Reached
Daily spending limit reached. Your progress has been saved.
Resume tomorrow when the daily limit resets.

Progress so far: 8 topics completed
Remaining: 7 topics

Your progress has been saved. To resume:
  deepr expert learn "Azure Architect" --resume
```

### 1. Expert Creation Budget
```bash
deepr expert make "Azure Architect" -f docs/*.md --learn --budget 5.00

# GPT-5 generates curriculum:
Learning Curriculum (15 topics):
1. Azure Landing Zone patterns       Est: $0.20, 10 min
2. Fabric architecture overview      Est: $0.15, 8 min
3. OneLake security models           Est: $0.25, 12 min
...
15. Fabric vs competitors            Est: $0.30, 15 min

Total: $3.45
Budget limit: $5.00  WITHIN BUDGET

Proceed? [y/N]
```

**Safety:**
- Show cost estimate per topic
- Show total cost and time
- Require confirmation if total > $1
- Hard fail if total > budget limit
- Pause if any single topic exceeds estimate by 2x

### 2. Conversation Budget
```bash
deepr chat expert "Azure Architect" --agentic --budget 3.00

Session budget: $3.00
Research triggered: "OneLake multi-tenant security" ($0.15)
Remaining: $2.85

[If expert wants to research again]
Expert: "I should also research Fabric capacity planning ($0.20).
Remaining budget: $2.65. Proceed? [y/N]"
```

**Safety:**
- Track cumulative research cost per session
- Warn when 80% budget consumed
- Block research when budget exhausted
- Show remaining budget after each research

### 3. Monthly Learning Budget
```bash
deepr expert set-learning-budget "Azure Architect" --monthly 10.00

# Expert can autonomously refresh knowledge up to $10/month
# Requires approval for:
#   - Individual research > $1
#   - Total monthly > budget
#   - Any learning outside user-initiated conversations
```

### 4. Emergency Controls
```bash
deepr expert pause "Azure Architect"   # Stop all autonomous activity
deepr expert resume "Azure Architect"  # Resume from saved progress
deepr expert reset-budget "Azure Architect"  # Reset monthly counter
deepr expert usage "Azure Architect"   # Show cost breakdown
```

### 5. Cost Alerts
```yaml
# config.yaml
expert_budgets:
  alert_threshold: 0.8  # Alert at 80% of budget
  auto_pause_threshold: 1.0  # Auto-pause at 100%
  monthly_report: true  # Email monthly usage report
```

**Alert Messages:**
```
[WARNING]  Expert "Azure Architect" has used $4.00 of $5.00 creation budget (80%)
[WARNING]  Session budget 90% consumed ($2.70 / $3.00). 1-2 more research topics remaining.
[BLOCKED] Monthly learning budget exhausted ($10.00 / $10.00). Expert paused until next month.
```

### 6. CLI Budget Validation (deepr/cli/validation.py)

The CLI validates budget inputs before operations:
- Warns for budgets > $10
- Requires confirmation for budgets > $25
- Shows daily/monthly spending status with `/status` command in expert chat

---

## Priority 3: MCP Server Integration (INFRASTRUCTURE) - Implementation Complete, Testing Needed

**Status**: Code implementation finished (2025-11-11). 7 tools implemented. Not yet tested with actual MCP clients.

**What This Means:**
- Code is written and imports successfully
- No automated tests exist for MCP functionality
- Not validated with Claude Desktop or Cursor in real scenarios
- Error handling untested with malformed requests
- Performance characteristics unknown

**What Was Built:**

An MCP server (`deepr/mcp/server.py`) that provides a stdio-based JSON-RPC interface for AI agents. The implementation includes 7 tools for research submission and expert consultation.

**Tools Implemented (7 total):**

Research tools (4):
1. `deepr_research` - Submit single research jobs with configurable model, provider, budget, and file uploads
2. `deepr_check_status` - Real-time job status polling with progress updates and cost tracking
3. `deepr_get_result` - Retrieve completed markdown reports with citations, metadata, and sources
4. `deepr_agentic_research` - Autonomous multi-step workflows where experts decompose goals and conduct research

Expert tools (3):
5. `deepr_list_experts` - List all domain experts with stats (documents, conversations, costs)
6. `deepr_query_expert` - Query experts with optional agentic mode for autonomous research triggers
7. `deepr_get_expert_info` - Get detailed expert metadata including vector store IDs and capabilities

**Architecture Decisions:**

Transport: stdio-based communication (lightweight, no dependencies, compatible with Claude Desktop/Cursor)
Job Tracking: In-memory per session with provider-side persistence for reliability
Multi-Provider: Supports OpenAI, Azure, Gemini, Grok through unified interface
Security: API keys in environment variables, budget controls, read-only operations
Error Handling: Structured error responses for all failure modes

**Strategic Insight:**

Deepr's async research fills a unique gap in the MCP ecosystem. Most MCP tools (Perplexity, Tavily) provide synchronous web search. Deepr provides asynchronous research infrastructure:
- Single research jobs: 5-20 minute comprehensive analysis
- Multi-step workflows: Expert-guided autonomous decomposition
- Expert consultation: Domain-specific knowledge with agentic capabilities

This positions Deepr as research infrastructure for AI agents, not just a human tool.

**Competitive Positioning:**

| Feature | Perplexity | Tavily | Deepr |
|---------|-----------|--------|-------|
| Research Model | Sync | Sync | Async |
| Multi-Step | No | No | Yes |
| Expert System | No | No | Yes |
| Agentic Mode | No | No | Yes |
| Budget Controls | Limited | Limited | Granular |
| Multi-Provider | No | No | Yes |

**Why Priority 3:**

Built on solid foundation from Priority 1 (semantic commands) and Priority 2 (expert system). The MCP integration leverages existing orchestration, making implementation straightforward and robust.

**MCP Server Interface:**

```python
# Tools exposed to AI agents via Model Context Protocol

deepr_research(
    prompt: str,
    sources: list = None,
    budget: float = None,
    files: list = None
) -> {job_id, estimated_time, cost_estimate}

deepr_check_status(job_id: str) -> {
    status,  # queued|running|completed|failed
    progress,  # phase information
    elapsed_time,
    cost_so_far
}

deepr_get_result(job_id: str) -> {
    status,
    markdown_report,  # full cited research
    cost_final,
    metadata
}

deepr_chat_expert(expert_name: str, question: str) -> {
    answer,
    sources,
    confidence
}

deepr_agentic_research(goal: str, sources: list, files: list) -> {
    job_id,
    workflow_plan
}
```

**Use Case Examples:**

```
# Agent working on competitive analysis
Agent: "I need deep research on competitor X's strategy"
- Calls deepr_research()
- Gets job_id, continues other work
- Periodically checks status
- When complete, retrieves comprehensive report
- Uses report to inform recommendations

# Agent with urgent question
Agent: "Quick - what's the latest on regulation Y?"
- Calls deepr_research(prompt="...", sources=["official sources"])
- Polls status every 2 minutes
- Gets result in ~5-10 minutes
- Responds to user with cited findings
```

**Implementation:**

1. **MCP Protocol Handler** (`deepr/mcp/server.py`):
   - Implements MCP protocol specification
   - Maps MCP tool calls to semantic commands (not `run focus`)
   - Handles async status polling
   - Returns structured responses

2. **Discovery & Registration**:
   - MCP manifest file describing capabilities
   - Auto-registration with MCP-compatible agents
   - Clear documentation for agent developers

3. **Security & Rate Limiting**:
   - API key authentication
   - Per-agent budget controls
   - Rate limiting to prevent abuse
   - Job ownership and access control

4. **Observability for Agents**:
   - Structured progress updates
   - Cost tracking per agent/session
   - Quality metrics (citation count, sources)

**Strategic Value:**

This positions Deepr as **research infrastructure for AI agents**, not just a human tool. When agents need comprehensive research (not just web search), they call Deepr.

**Competitive Advantage:**
- Perplexity: Real-time search (sync)
- Tavily: Web search API (sync)
- **Deepr: Comprehensive research infrastructure (async)** ← Unique position

**Implementation Details:**

Location: `deepr/mcp/server.py` (489 lines)
Configuration templates: `mcp/mcp-config-claude-desktop.json`, `mcp/mcp-config-cursor.json`
Documentation: `mcp/README.md`

The server implements stdio-based JSON-RPC communication with async Python. Job tracking is in-memory per session, with jobs persisting on the provider side.

**What Works (Validated):**
- Server imports and initializes without errors
- Code structure follows MCP stdio patterns
- Integration with existing Deepr orchestration layer

**What Needs Validation:**
- Actual communication with Claude Desktop/Cursor
- Error handling with malformed requests
- Job status polling reliability
- Agentic research workflow execution
- Multi-provider operations
- Cost tracking accuracy
- Performance under concurrent requests

**Testing Gaps:**
- No unit tests for MCP tools
- No integration tests with MCP clients
- No load testing
- Error scenarios not covered

**Next Steps to Consider Production-Ready:**
1. Test with Claude Desktop installation
2. Validate all 7 tools work end-to-end
3. Add automated tests
4. Test error scenarios
5. Validate concurrent request handling
6. Document observed performance characteristics

---

## Priority 4: Observability by Design (TRANSPARENCY)

Machine-readable transparency with human-friendly views.

**Implementation:**

1. **Automatic Metadata Generation**:
   - Every task emits structured JSON: prompt, context used, model, tokens, cost
   - Reasoning timelines auto-generated from phase transitions
   - Context lineage graph built automatically from dependencies
   - Zero manual logging, full auditability

2. **Tiered Transparency** - Machine-first, human on demand:
   ```bash
   deepr get <job-id>                    # Clean summary (default)
   deepr get <job-id> --explain          # Why this path?
   deepr get <job-id> --timeline         # Reasoning evolution
   deepr get <job-id> --full-trace       # Complete audit (JSON)
   ```

3. **Cost Attribution Dashboard**:
   - Auto-tracked per phase, per perspective, per provider
   - Cost/insight ratio analysis
   - Budget alerts and trend visualization

4. **Planner Decision Logs**:
   - "I chose to research X before Y because [gap analysis]"
   - "Reviewer identified: missing market data, requested Phase 2"
   - Natural language explanations generated automatically

**Acceptance Criteria:**
- [TODO] All tasks emit structured metadata automatically
- [TODO] `--explain`, `--timeline`, `--full-trace` flags work
- [TODO] Cost dashboard tracks per-phase costs
- [TODO] Decision logs are human-readable

---

## Priority 5: Autonomous Provider Routing (OPTIMIZATION)

Move from rule-based to continuously optimized selection.

**Implementation:**

1. **Real-Time Benchmarking**:
   - Track per provider: cost, latency, citation quality, success rate
   - Rolling 30-day performance stats
   - Auto-select best provider per task type

2. **Resilience & Fallback**:
   - Auto-retry with alternate provider on failure/timeout
   - Graceful degradation (cheaper model fallback if primary unavailable)
   - Auto-resume campaigns after provider recovery

3. **Provider Health Monitoring**:
   - Detect degraded performance, adjust routing
   - User notifications only on failures

**Configuration:**
```bash
# User provides keys once
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

# System handles everything
deepr research "topic"  # Auto-routes, auto-retries, auto-optimizes
```

**Acceptance Criteria:**
- [TODO] Provider selection based on performance metrics
- [TODO] Auto-fallback on provider failures
- [TODO] Performance tracking dashboard

---

## Priority 7: NVIDIA Provider Support (CONSUME, NOT BUILD)

**Status**: Research completed (November 2025). Implementation: Later priority.

**Deepr's Scope**: If you have NVIDIA infrastructure deployed, Deepr can consume it. We will NOT build, deploy, or manage NVIDIA infrastructure.

**Key Finding**: NVIDIA doesn't offer a single managed API like OpenAI. Instead, enterprises deploy their own NVIDIA stack (NIM microservices, NeMo, Nemotron models). Once deployed, these expose OpenAI-compatible APIs.

**What Deepr Would Support**:

```bash
# User already has NVIDIA NIM deployed at: http://datacenter.company.com/nim/v1
# Deepr just needs to point to it

deepr research "Topic" --provider nvidia --model nemotron-70b
```

**Implementation** (when prioritized):

```python
# Create NvidiaProvider that consumes existing infrastructure
class NvidiaProvider(DeepResearchProvider):
    def __init__(self, base_url: str, api_key: str):
        # User provides their self-hosted NIM endpoint
        self.base_url = base_url  # e.g., "http://datacenter.company.com/nim/v1"
        # Use OpenAI-compatible client (NVIDIA NIMs expose /v1/chat/completions)
        self.client = OpenAI(base_url=base_url, api_key=api_key)
```

**What User Must Have** (out of Deepr's scope):
1. NVIDIA NIM containers deployed in their datacenter/cloud
2. NeMo Agent Toolkit for custom workflows (if needed)
3. Nemotron models running and accessible via API
4. NeMo Guardrails configured for their requirements
5. Infrastructure team managing the NVIDIA stack

**Deepr's Requirements from NVIDIA Setup**:
- OpenAI-compatible API endpoint (`/v1/chat/completions`)
- Model name/identifier for requests
- API key or auth mechanism
- That's it. We consume the API, nothing more.

**Why This Is Lower Priority**:
- **Niche Use Case**: Only for enterprises with self-hosted NVIDIA infrastructure
- **Small User Base**: Most users will use managed APIs (OpenAI, Gemini, Grok)
- **Same API Surface**: NVIDIA NIMs expose OpenAI-compatible endpoints, so integration is straightforward when needed
- **Current Focus**: Solidify managed cloud provider experience first

**When to Prioritize**:
- When users explicitly request: "I have NVIDIA NIM deployed, can Deepr use it?"
- After core features (MCP, observability, semantic commands) are stable
- When enterprises adopt Deepr and need on-prem integration

**Clear Boundary**: Deepr is a research automation tool, not an infrastructure provisioning tool. We assume NVIDIA infrastructure exists and is managed by the user's ops team.

See: `docs/research nvidia deep research.txt` for complete technical analysis of NVIDIA's ecosystem.

---

## Priority 6: Context Discovery (ADVANCED FEATURE)

**Critical principle: Context is everything. Bad context = bad research. Default to fresh research.**

**Default Behavior:**
- Never auto-reuse context
- Only discover and notify (user decides)
- High friction by design (quality over convenience)

**Implementation:**

1. **Detection (Optional, Disabled by Default)**:
   ```bash
   deepr research "Research Ford's EV strategy" --check-related

   INFO: Found potentially related research:
   - "EV market trends 2025" (Sep 15, $2.40, o1, 47 cites) [You rated: 4/5]
   - "Tesla competitive analysis" (Aug 20, $1.80, o1-mini, 23 cites) [Not rated]

   Continue with fresh research? [Y/n]
   ```

2. **Explicit Reuse Only**:
   ```bash
   deepr research "..." --reuse-context job-123,job-456

   WARNING: Reusing prior research
   - job-123: "EV market trends" (Sep 15, $2.40, 12K tokens)
   - job-456: "Tesla analysis" (Aug 20, $1.80, 8K tokens)

   Context injection can poison results if research is shallow/outdated.
   Proceed? [y/N]  # Default is NO
   ```

**Why Extreme Bias Against Reuse:**
- Context quality determines research quality
- Shallow research on wrong topic/perspective/timeframe is worse than no context
- Cost savings from reuse (~30-70% tokens) not worth quality degradation
- Better to over-research than to confidently deliver garbage

**v3.0+ Only:** After 1000+ campaigns, IF we can prove quality preservation:
- ML-based quality scoring (train on user ratings)
- "What's new since job-123?" delta research mode
- Smart reuse suggestions (still requires user approval)

---

## v2.2 Summary: Build Order

1. [DONE] **Fix stale status refresh** - Done
2. [DONE] **Fix campaign grouping** - Jobs now grouped cleanly by campaign type
3. [DONE] **Priority 2 (Phase 1)**: Core semantic commands (`research`, `learn`, `team`) - DONE
4. [DONE] **Intuitive Terminology**: Added `deepr brain` and `deepr knowledge` aliases - DONE
5. [DONE] **Priority 2.5 (Phase 1a)**: Expert system foundation (`expert make/list/info/delete`) - DONE
6. [DONE] **Priority 2.5 (Phase 1b)**: Self-directed learning curriculum (`--learn --budget --topics`) - DONE
7. [DONE] **Priority 1**: UX Polish - CLI-first experience improvements - DONE
8. [DONE] **Priority 2.5 (Phase 2)**: Interactive expert chat (`expert chat`) - DONE
9. [TODO] **Priority 2.5 (Phase 3)**: Agentic research integration (`expert chat --agentic`)
10. [TODO] **Priority 2 (Phase 2)**: Additional semantic commands (`check`, `make docs`, `make strategy`)
11. [TODO] **Priority 3**: MCP Server - Expose via Model Context Protocol
12. [TODO] **Priority 4**: Observability - Transparency and tracing
13. [TODO] **Priority 5**: Provider Routing - Auto-optimization
14. [TODO] **Priority 6**: Context Discovery - Advanced (optional)
15. [TODO] **Priority 7**: NVIDIA Self-Hosted Provider - Enterprise sovereign stack (later)

**Key Principle:** Build solid foundation before adding advanced features. CLI-first experience is foundational.

**Progress Update (2025-11-05):**
- [DONE] Semantic interface launched with 3 core commands
- [DONE] Expert system architecture complete (profile storage, management commands)
- [DONE] Autonomous learning curriculum generation (GPT-5 + Responses API)
- [DONE] Multi-layer budget protection for autonomous learning
- [DONE] Temporal knowledge tracking with domain velocity awareness
- [DONE] CLI UX polish: cross-platform paths, diagnostics, progress feedback
- [DONE] Interactive expert chat mode with conversation management
- [DONE] Comprehensive test coverage (71 tests, 0 API calls)
- [TODO] Next: Agentic research capabilities for experts
- [TODO] Then: Additional semantic commands
**v2.3: Dream Team - Cognitive Diversity Made Visible**

**Status: CORE IMPLEMENTED** - Dynamic team assembly working, observability in progress

**The Insight:** Deepr already works like a research team with diverse perspectives. We just need to make that visible and controllable.

**IMPLEMENTED: Dynamic Dream Team**

```bash
deepr team analyze "Should we pivot to enterprise?" --team-size 5

# Phase 1: GPT-5 assembles optimal team for THIS question
# Team changes based on what the question actually needs
# Example for enterprise pivot:
#   - Enterprise SaaS Market Analyst (quantitative data)
#   - Former Enterprise Procurement Lead (buyer perspective)
#   - Head of Product-Led Sales (execution path)
#   - CFO from high-growth SaaS (unit economics)
#   - Enterprise Customer (honest feedback)

# Phase 2: Each member researches independently from their role
# Phase 3: Lead Researcher synthesizes with attribution
# Shows: agreements, conflicts, balanced recommendations

# Result: See the debate AND the conclusion
```

**Key Design Principle:** Fully dynamic, not static personas. GPT-5 determines optimal team composition for each specific question. "Should we pivot to enterprise?" gets a different team than "How do we compete with Notion?"

**What Works Now:**
- Dynamic team assembly (GPT-5 designs team per question)
- Role-specific research tasks (each member stays in their lane)
- Synthesis with attribution (credit team members)
- Conflict highlighting (where perspectives disagree)
- Grounded personas (research actual company leadership)
- Cultural/demographic lens (analyze through any perspective)
- Adversarial mode (weight team toward skeptical perspectives)

**Examples:**

```bash
# Balanced analysis
deepr team analyze "Should we pivot to enterprise?" --team-size 5

# Devil's advocate mode (weighted toward skeptical perspectives)
deepr team analyze "Our Q2 launch plan" --adversarial

# Grounded in actual company leadership
deepr team analyze "What's Anthropic's AI strategy?" --company "Anthropic"

# Cultural/demographic perspective lens
deepr team analyze "Market expansion strategy" --perspective "Japanese business culture"
deepr team analyze "Product positioning" --perspective "Gen Z"
```

**Future Enhancements:**

1. **Enhanced Observability** - Make reasoning traces visible:
   - Show Extended Thinking traces from Anthropic provider
   - Tag findings by team member role
   - Highlight where perspectives converge vs diverge
   - Cost breakdown per team member

3. **Depth Control** - Choose how much debate you want:
   ```bash
   --depth quick    # Just gather facts, minimal synthesis
   --depth balanced # Current default, all perspectives
   --depth adversarial # Maximum debate, challenge everything
   ```

**Why This Matters:**

Diverse perspectives catch blind spots. The Optimist alone would miss risks. The Skeptic alone would miss opportunities. Real research teams work because people with different cognitive styles challenge each other.

Deepr automates that dynamic. But right now, users only see the final synthesis—they miss the creative tension that made it good. v2.3 makes the dream team visible:

- See which perspectives contributed what
- Understand why conclusions are balanced
- Spot when one voice dominates (might be a problem)
- Control how much debate you want

**Observability & Trust Principles:**

Following "Design for Trust" research (Agentic AI Engineering):

1. **Glass Box Transparency** - Show the work, not just results:
   - Reasoning traces visible (Extended Thinking, o3 reasoning tokens)
   - Source attribution for every finding
   - Decision logs (why Planner chose tasks, why Reviewer requested next phase)
   - Cost breakdown per task

2. **Semantic Traces** - Make debugging and auditing trivial:
   - Every task tracks: prompt, context used, model, tokens, cost
   - Phase results persist: what was learned, what gaps remain
   - Link findings back to source tasks

3. **No Hidden Reasoning** - Free speech for AI perspectives:
   - Never hide or censor AI reasoning
   - Surface conflicts between perspectives openly
   - Trust users to evaluate evidence themselves
   - Provide full context, not filtered summaries

4. **Observability Without Noise** - Clean but complete:
   - Primary UX stays minimal (no distracting verbosity)
   - But ALL details available on demand (`--verbose`, debug logs)
   - Web UI shows reasoning traces in expandable sections
   - Export full audit trails for compliance

This builds trust through transparency while keeping UX clean.

**The Technical Foundation (for the curious):**

We built robust orchestration without realizing it:
- Conductor (BatchExecutor) manages workflow
- Structured communication (research_plan.json)
- Context flows between phases (ContextBuilder)
- Adaptive review cycles (ResearchReviewer)

That's why Deepr works—we solved the hard orchestration problems first. Now we make the magic visible.

## Non-Goals

Explicitly NOT building:
- Chat interface (use regular GPT)
- Real-time responses (deep research takes minutes by design)
- Sub-$1 research (comprehensive research costs money)
- Mobile apps (CLI/web sufficient)
- Complex export formats (markdown is clean and simple)
- Features that might not work reliably
- Vendor lock-in or favoring one provider over another

## Philosophy

Every feature should:
- Support long-running research workflows
- Build context across research phases
- Synthesize insights from multiple sources
- Save users from manual integration work
- Work across providers (platform, not wrapper)

Focus on:
- Intelligence layer (planning, sequencing, synthesis, routing)
- Clean, simple outputs (markdown)
- Reliable execution
- Cost transparency
- Provider flexibility

Not on:
- Complex formatting that might break
- Premature optimization
- Features without clear value
- Vendor lock-in

## The Core Insight

Most AI tools give answers. Deepr gives understanding.

Difference:
- Answers are isolated facts
- Understanding comes from seeing connections
- Connections emerge from context chaining
- Context chaining requires intelligent sequencing

Agentic planning is profound because it automates research strategy, not just research execution.

## Dogfooding

We use Deepr to build Deepr. When we hit implementation questions:
- Formulate research question
- Submit to Deepr
- Get comprehensive answer with citations
- Implement based on findings
- Document the research

This validates the tool while generating implementation guidance.

Recent example: "Research best practices for context injection in multi-step LLM workflows"
- Cost: $0.17, Tokens: 94K
- Result: 15KB comprehensive report with inline citations
- Key findings: Summarization cuts tokens by ~70%, prevents context dilution, improves quality
- Direct impact: Validated our ContextBuilder design, informed Phase 2 prompt engineering
- ROI: Implementation guidance that would require extensive manual research

This is proper dogfooding - using Deepr to research how to build Deepr's core features.

## Contributing

High-value areas:
- Context chaining logic
- Synthesis prompts (integrating findings)
- Cost optimization
- Template patterns (proven research strategies)

Most impactful work is on intelligence layer, not infrastructure.

---

## Summary: Roadmap Evolution

**What Changed:**

Previous roadmap focused on horizontal expansion:
- More providers (Anthropic, Azure, Google when available)
- More features (templates, exports, UI improvements)
- More infrastructure (monitoring, deployment)

**New roadmap trajectory: Agentic Level 3 to Level 5**

| Version | Agentic Level | Focus |
|---------|---------------|-------|
| v2.1 (current) | **Level 3** | Adaptive planning with feedback |
| v2.2-2.3 | **Level 3 to 4** | Transparent automation + observability |
| v2.4 | **Level 4** | Reflective optimization (memory, verification) |
| v3.0+ | **Level 5** | Autonomous meta-researcher |

**Current State (v2.1 - Level 3):**
- Adaptive research workflow (plan - execute - review - replan) [DONE]
- Context chaining with smart task mix [DONE]
- Dream team dynamic assembly [DONE]
- GPT-5 planner adjusts based on findings [DONE]

**Path to Level 4 (v2.2-v2.4):**

- **v2.2: Transparent Automation Foundation**
  - Observability by design (auto-metadata, reasoning logs)
  - Context discovery (notify, don't auto-inject - quality first)
  - Autonomous provider routing (benchmarking, auto-fallback)
  - Human oversight when needed (checkpoints, intervention)
  - **Web Scraping Skill** (Primary source acquisition) [DONE]
    - Adaptive fetching: HTTP - Selenium - PDF render - Archive.org
    - LLM-guided link filtering (not blind crawling)
    - Content synthesis with provenance tracking
    - Use cases: company research, documentation harvesting, competitive intel
    - Integration: Python API (`deepr.utils.scrape`) ready for research workflows
    - Philosophy: Get the content (research-focused, user control over guardrails)
    - Status: COMPLETE - 2,491 lines, all tests passing, real-world validated
  - **Strategic Company Research** (Foundational use case) [TODO]
    - One-command company analysis: `deepr research company <company_name> <website>`
    - 15-section comprehensive report (products, financials, strategy, board concerns, recommendations)
    - Orchestrates: Web scraping - Google search - Section research - Quality grading - Final report
    - Proven prompts from existing Automated Company Researcher (47 prompts)
    - Output: Professional markdown report ready for M&A, competitive intel, strategic planning
    - Expert integration: Company research - Expert knowledge base (e.g., "Anthropic Expert")
    - Use cases: Due diligence, competitive analysis, market research, strategic planning
    - Status: Design complete, prompts ready, orchestration needed
  - **Grok as Cost-Effective Default** (Reduce GPT-5 dependency) [IN PROGRESS]
    - Strategy: Use Grok 4 Fast for non-deep-research operations
    - Deep Research: OpenAI o3/o4-mini (only provider with async Deep Research API)
    - Everything else: Grok 4 Fast (47x cheaper than GPT-5, SOTA cost-efficiency)
    - Planning/synthesis/chat: Grok 4 Fast ($0.20 input / $0.50 output per 1M tokens)
    - Expert systems: Grok 4 Fast with tool calling (web_search, x_search, code_execution)
    - Research orchestration: Grok 4 Fast for adaptive planning and review
    - Context building: Grok 4 Fast for summarization (vs gpt-5-mini)
    - Link filtering (scraping): Grok 4 Fast for relevance scoring
    - Benefits:
      * 98% cost reduction vs GPT-5 at comparable intelligence
      * 2M token context window (vs GPT-5's limits)
      * Native X search integration (real-time social intelligence)
      * Agentic tool calling (autonomous web/code/X search)
      * Unified reasoning/non-reasoning in single model
    - Implementation:
      * Update default models in config
      * Test and validate Grok 4 Fast across all workflows
      * Keep OpenAI for Deep Research (unique capability)
      * Measure quality vs cost trade-offs
      * Fallback to GPT-5 if Grok unavailable
    - Status: Provider complete, defaults need updating, testing in progress

- **v2.3: Cognitive Diversity Visibility**
  - Show team member contributions and conflicts
  - Reasoning timeline visualization
  - Context lineage graphs
  - Trust through transparency

- **v2.4: Reflective Optimization**
  - Research discovery (embedding-based, notify-only default)
  - Basic verification (contradiction detection, citation metrics)
  - Performance benchmarking (what works, what doesn't)
  - Ecosystem integrations and developer SDK

**Path to Level 5 (v3.0+):**
- Continuous evaluation loop (self-assessment of quality)
- Self-optimizing planner (learns from outcomes)
- Advanced verification (self-correction)
- Full cognitive autonomy (closed loop: perceive - plan - act - evaluate - update)

**Core Principles:**

1. **Quality Over Everything**
   - Context is everything: Bad context = bad research
   - Default to fresh research, always
   - No automatic reuse - ever (not in v2.x)
   - Cost "savings" from reuse aren't worth quality degradation
   - Better to over-research than confidently deliver garbage

2. **Library, Not Memory**
   - "Memory" implies automatic reuse (dangerous)
   - "Library" is reference material (safe)
   - Pull-based search, never push-based suggestions
   - User searches, reads, judges, decides
   - System never assumes prior research is good enough

3. **Transparency Enables Autonomy**
   - Users trust what they understand
   - Observability first, then automation
   - Make reasoning visible before making decisions autonomous
   - Extreme quality bias now - enables trust for autonomy later

4. **Incremental Autonomy**
   - Level 3 to 4: Build trust through transparency (v2.2-2.4)
   - Level 4 to 5: Enable self-improvement (v3.0+)
   - Never sacrifice quality for automation
   - Prove quality preservation before enabling smart reuse (v3.0+, if ever)

5. **Local-First, Provider-Agnostic**
   - Best tool for each task, no vendor lock-in
   - Self-hosted knowledge and benchmarks
   - User controls data and decisions
