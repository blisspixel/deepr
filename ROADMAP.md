# Deepr Development Roadmap

## Model Strategy

**Multi-Provider Architecture with GPT-5 Standard**

Deepr supports multiple AI providers for flexibility and avoiding vendor lock-in:
- **OpenAI**: Primary provider using **GPT-5 models** (gpt-5, gpt-5-mini, gpt-5-nano)
- **Azure OpenAI**: Enterprise version using **GPT-5** via Azure
- **Google Gemini**: Alternative provider (2.5-flash, 2.5-pro)
- **xAI Grok**: Real-time search capabilities

**Important**: When using OpenAI or Azure OpenAI, Deepr **uses GPT-5 models only**. We do not support GPT-4.
- Expert systems: GPT-5 with tool calling for RAG (NOT deprecated Assistants API)
- Research planning: GPT-5 for curriculum generation and adaptive workflows
- Chat interfaces: GPT-5 with tool-based vector store retrieval

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

Deepr's approach: **Plan → Execute → Review → Plan next phase**

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
# Cost: ~$3-5, Time: 40-50 minutes
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
  - Submit query → get comprehensive report (asynchronous)
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
- Adaptive workflows (Plan → Execute → Review → Replan)
- Dream team dynamics (diverse cognitive perspectives)
- All via simple CLI (no complex orchestration needed)

**Future Vision:**
When other providers launch Deep Research APIs, Deepr will intelligently route:
- Quick documentation → o4-mini (fast, cheap)
- Deep analysis → o3 or competitor equivalent
- Planning → GPT-5 or Claude Extended Thinking
- Auto-fallback if provider unavailable

Testing:
- Generate plans for various scenarios
- Validate doc reuse logic works
- Measure cost savings from reusing docs
- Use Deepr itself to research optimal strategies

## Future: Toward Agentic Level 5

**Vision:** Transform Deepr from an adaptive planning system (Level 3) into a fully autonomous, self-improving meta-researcher (Level 5).

**Agentic Levels Framework:**

| Level | Description | Deepr Status |
|-------|-------------|--------------|
| 1 | **Reactive Execution** - Single-turn, no planning | Exceeded |
| 2 | **Procedural Automation** - Scripted sequences | Exceeded |
| 3 | **Adaptive Planning** - Plans and adjusts based on feedback | **Current (v2.1)** |
| 4 | **Reflective Optimization** - Learns from outcomes, self-tunes | **Target (v2.2-2.4)** |
| 5 | **Autonomous Meta-Researcher** - Self-directing, goal-defining | **Future (v3.0+)** |

**Level 5 Requirements (the closed cognitive loop):**

1. **Perceive** - Detect research needs and quality gaps automatically
2. **Plan** - Generate optimal research strategies without templates
3. **Act** - Execute research with autonomous provider/task selection
4. **Evaluate** - Score outcomes, detect shallow/incorrect research
5. **Update Self** - Improve planning heuristics based on results

**Roadmap Alignment:**

- **v2.2-2.3: Foundation for Level 4**
  - Observability by design (understand what the system does)
  - Autonomous routing and context discovery (reduce manual work)
  - Human oversight when needed (trust-building)

- **v2.4: Emerging Level 4**
  - Lightweight memory (learn from past research)
  - Basic verification (detect quality issues)
  - Performance benchmarking (measure what works)

- **v3.0+: Achieve Level 5**
  - Continuous evaluation loop (self-assessment)
  - Self-optimizing planner (autonomous strategy improvement)
  - Advanced verification (self-correcting research)
  - Full cognitive autonomy (human sets goals, system handles everything else)

**Critical Principle: Quality Over Automation**

- Notify, don't auto-inject (context discovery vs. blind reuse)
- Bias toward over-research, not cost savings
- Transparent by default, autonomous where proven
- Human judgment for quality, machine execution for scale

**Strategic Shift:** Previous roadmap emphasized adding providers and features. This refined roadmap builds toward Level 5:
1. **Observability** - Make reasoning visible and understandable (trust foundation)
2. **Autonomy** - Context discovery, provider routing, metadata tracking (reduce manual work)
3. **Learning** - Benchmarking, scoring, feedback loops (reflective optimization)
4. **Meta-intelligence** - Self-improving strategies, goal-driven research (Level 5)

**Priorities:**
- v2.2: Transparent automation + observability (Level 3 → Level 4 foundation)
- v2.3: Cognitive diversity made visible (trust through transparency)
- v2.4: Memory + verification basics (emerging Level 4)
- v3.0+: Continuous learning + meta-research (achieve Level 5)

**v2.2: Intelligence Layer - Transparent Automation**

Focus: Fix broken UX → Clean interface → Expose via MCP → Add observability → Optimize

**Build Order Philosophy:** Foundation → Interface → Infrastructure → Observability → Optimization

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
[Cost: $0.15, Time: ~8 minutes]

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

Cost: $8.45 | Time: 35 minutes
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

**Phase 1a: Expert Management** [DONE] DONE
- Expert profile storage
- Create/list/info/delete commands
- Vector store integration
- Beginner's mind system message

**Phase 1b: Self-Directed Learning Curriculum** [IN PROGRESS]
- `deepr expert make "name" -f files --learn --budget 5`

**COMPLETED:**
- [DONE] GPT-5 curriculum generation (Responses API with GPT-5)
- [DONE] Deep research job submission (o4-mini-deep-research)
- [DONE] Budget estimation shown upfront (per-topic + total)
- [DONE] Multi-layer budget protection (curriculum + per-job validation)
- [DONE] Research prompt length validation (<300 chars for API compatibility)
- [DONE] Phased execution respecting topic dependencies
- [DONE] Expert tracking of research job IDs

**CURRENT STATUS (2025-11-06 - WORKING):**

**Autonomous learning workflow is fully functional:**
- [DONE] Research jobs ARE submitted successfully to OpenAI
- [DONE] Jobs DO complete (4-20 min each, $0.10-0.30 per job)
- [DONE] Polling for completion implemented ([learner.py:236-335](deepr/experts/learner.py#L236-L335))
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

**Phase 4: Continuous Self-Improvement** [TODO] v2.3+
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
- Query → retrieve → answer
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
- Knowledge base auto-update: IN PROGRESS (research → permanent learning)
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

Total: $3.45, ~2.5 hours
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
deepr expert resume "Azure Architect"  # Resume
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

---

## Priority 3: MCP Server Integration (INFRASTRUCTURE) - ✅ COMPLETE

**Status**: Implementation complete (2025-11-11). See `MCP_SETUP.md` for usage.

**Strategic insight:** Deepr's async research fills a unique gap - most MCP tools are synchronous.

**Why Priority 3 (not 0):** Build on solid foundation (P1) with clean interface (P2) first.

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
→ Calls deepr_research()
→ Gets job_id, continues other work
→ Periodically checks status
→ When complete, retrieves comprehensive report
→ Uses report to inform recommendations

# Agent with urgent question
Agent: "Quick - what's the latest on regulation Y?"
→ Calls deepr_research(prompt="...", sources=["official sources"])
→ Polls status every 2 minutes
→ Gets result in ~5-10 minutes
→ Responds to user with cited findings
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

**Acceptance Criteria:**
- [✅] MCP server runs and registers with agents
- [✅] All MCP tools use semantic interface (not implementation modes)
- [✅] Async status polling works reliably
- [✅] Cost tracking per agent/session
- [✅] Documentation for agent developers
- [✅] Multi-provider support (OpenAI, Azure, Gemini, Grok)
- [✅] Expert chat integration
- [✅] Security guidelines implemented

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
- Cost: $0.17, Time: 6 minutes, Tokens: 94K
- Result: 15KB comprehensive report with inline citations
- Key findings: Summarization cuts tokens by ~70%, prevents context dilution, improves quality
- Direct impact: Validated our ContextBuilder design, informed Phase 2 prompt engineering
- ROI: Implementation guidance that would have taken hours of manual research

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

**New roadmap trajectory: Agentic Level 3 → Level 5**

| Version | Agentic Level | Focus |
|---------|---------------|-------|
| v2.1 (current) | **Level 3** | Adaptive planning with feedback |
| v2.2-2.3 | **Level 3 → 4** | Transparent automation + observability |
| v2.4 | **Level 4** | Reflective optimization (memory, verification) |
| v3.0+ | **Level 5** | Autonomous meta-researcher |

**Current State (v2.1 - Level 3):**
- Adaptive research workflow (plan → execute → review → replan) [DONE]
- Context chaining with smart task mix [DONE]
- Dream team dynamic assembly [DONE]
- GPT-5 planner adjusts based on findings [DONE]

**Path to Level 4 (v2.2-v2.4):**

- **v2.2: Transparent Automation Foundation**
  - Observability by design (auto-metadata, reasoning logs)
  - Context discovery (notify, don't auto-inject - quality first)
  - Autonomous provider routing (benchmarking, auto-fallback)
  - Human oversight when needed (checkpoints, intervention)

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
- Full cognitive autonomy (closed loop: perceive → plan → act → evaluate → update)

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
   - Extreme quality bias now → enables trust for autonomy later

4. **Incremental Autonomy**
   - Level 3 → 4: Build trust through transparency (v2.2-2.4)
   - Level 4 → 5: Enable self-improvement (v3.0+)
   - Never sacrifice quality for automation
   - Prove quality preservation before enabling smart reuse (v3.0+, if ever)

5. **Local-First, Provider-Agnostic**
   - Best tool for each task, no vendor lock-in
   - Self-hosted knowledge and benchmarks
   - User controls data and decisions
