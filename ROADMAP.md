# Deepr Development Roadmap

## Vision: Agentic Research Automation

Deepr is an intelligent research system that:
- Reasons about information needs
- Plans multi-phase research campaigns
- Sequences tasks based on dependencies
- Chains context across research phases
- Synthesizes insights that span multiple findings

This creates analysis greater than the sum of its parts.

## Current Status

### v2.0: Core Infrastructure (Complete)

Working now:
- SQLite queue with all operations
- Local filesystem storage
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
- "Document latest OpenAI Deep Research API pricing and features (2025)"
- "Compile comprehensive list of Python async/await patterns"
- Purpose: Create factual reference materials
- Cheaper, faster (factual gathering)

Analysis tasks (generate insights):
- "Analyze trade-offs between SQLite and PostgreSQL for queue backend"
- "Evaluate cost-effectiveness of different LLM providers for batch processing"
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

We're dogfooding: Used Deepr to analyze its own docs, identified 8 gaps, queued 6 research jobs. Cost: $3-12, Time: 60-120 minutes.

## Building Next: Intelligent Doc Reuse & Planner Enhancements

Now that context chaining is implemented, focus is on making the planner smarter about task mix and avoiding redundant research.

**Doc Reuse Intelligence** (Priority 1)

Before generating a plan, use GPT-5 to check existing docs:
- Scan docs/ directory for relevant research
- Ask GPT-5: "Is this existing doc sufficient for the scenario? Or do we need updated/better research?"
- If sufficient: Include in context, skip redundant task
- If outdated: Queue new research with clear prompt (e.g., "Update X with 2025 data")
- If insufficient: Queue deeper research with specific gaps to address

Implementation:
```python
class DocReviewer:
    def check_existing_docs(self, scenario: str) -> List[Dict]:
        # Scan docs/research and documentation/
        # Use GPT-5 to evaluate relevance and sufficiency
        # Return: [{"path": ..., "relevant": bool, "gaps": str}]
```

Benefits:
- Save money by reusing existing research
- Update only what's outdated
- Build on prior work instead of starting from scratch

**Planner Enhancements** (Priority 2)

Task mix improvements (already implemented):
- Distinguish documentation vs analysis tasks
- Cost-awareness (docs ~30% cheaper)
- Different prompts for each type

Additional needed:
- Skip obvious/low-value tasks
- Better dependency reasoning
- Cost-benefit analysis per task

**Market Context** (Based on competitive analysis)

Provider landscape:
- **OpenAI**: Market leader, turnkey deep research API (our current focus)
- **Azure OpenAI**: Enterprise version with Bing Search integration
- **Anthropic**: SDK approach with Extended Thinking, more control
- **Google**: Batch API for high-throughput parallel tasks (different use case)
- **Perplexity**: Real-time search API (different use case)

**Our Position: Provider-Agnostic Platform**

Deepr is NOT a wrapper for one API - it's a research automation platform that works with multiple providers.

Current status:
- OpenAI fully implemented (most mature offering)
- Azure OpenAI supported (same backend)
- Anthropic planned (SDK integration)
- Architecture designed for multi-provider support

Our unique value:
- Not just "one prompt → one report" (that's commodity)
- Intelligent multi-phase planning with context chaining
- Smart mix of documentation + analysis
- Doc reuse to minimize cost
- Provider-agnostic (use best provider for each task)
- All via simple CLI (no complex orchestration needed)

Long-term vision: When you have multiple provider keys configured, Deepr intelligently routes each task to the best provider:
- Quick documentation gathering → o4-mini (fast, cheap)
- Deep analysis → o3 or Claude with Extended Thinking (thorough)
- Synthesis → Best model available
- Auto-fallback if one provider is down

Testing:
- Generate plans for various scenarios
- Validate doc reuse logic works
- Measure cost savings from reusing docs
- Use Deepr itself to research optimal strategies

## Future: Multi-Provider Support

**v2.2: Additional Providers**

Implement support for alternative providers:

Anthropic integration:
- Claude Agent SDK adapter
- Extended Thinking for complex analysis
- Custom tool support
- Developer-managed agentic loop

Provider routing logic:
- Auto-select best provider per task type
- Consider: cost, speed, quality, availability
- Fallback if provider unavailable
- User override: `--provider anthropic`

Example intelligent routing:
```python
# Documentation task (cheap, fast)
if task.type == "documentation":
    provider = "openai-o4-mini"  # Fastest, cheapest

# Deep analysis (thorough)
elif task.type == "analysis" and task.complexity == "high":
    provider = "anthropic-claude-extended"  # Extended Thinking

# Synthesis (integrate findings)
elif task.type == "synthesis":
    provider = "openai-o3"  # Best synthesis
```

Configuration:
```bash
# User provides multiple keys
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

# Deepr automatically uses best provider per task
deepr prep execute  # Auto-routes each task
```

**v2.3: Platform Maturity**

CLI improvements:
- Output formatting options (JSON, markdown)
- Better progress indicators

Worker improvements:
- Service setup (systemd/Windows)
- Health checks
- Auto-restart

Web UI improvements:
- Results library (browse completed research)
- Job detail pages with full output
- Real-time job progress indicators
- Export results (PDF, DOCX)

Templates:
- Pre-built patterns (market analysis, due diligence, competitor analysis)
- Custom template creation
- Template library

Cost management:
- Budget tracking and alerts
- Usage analytics
- Per-provider cost comparison

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

**Current focus:**
- v2.1: Context chaining with smart task mix and doc reuse
- OpenAI as primary provider (most mature)
- Architecture designed for multi-provider support

**Future focus:**
- v2.2: Add Anthropic provider with intelligent routing
- v2.3: Platform maturity (templates, cost management, monitoring)

**Philosophy:** Research automation platform, not vendor wrapper. Best provider for each task, no lock-in.
