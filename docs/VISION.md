# Deepr Vision

> **Note**: This document describes aspirational goals, not current capabilities. See [ROADMAP.md](../ROADMAP.md) for what's actually implemented.

## The Goal

Transform research from isolated queries into cumulative understanding. Build systems that learn and improve over time.

## Current State (v2.9.1)

What works today:
- Multi-provider deep research (OpenAI, Gemini, Grok, Anthropic, Azure)
- Gemini Deep Research Agent via Interactions API
- Multi-phase research with context chaining
- Domain experts from documents with autonomous learning
- Agentic expert chat with streaming, 27 slash commands, 4 chat modes, visible reasoning, context compaction, approval flows
- Expert council (multi-expert consultation with parallel querying and synthesis)
- Hierarchical task decomposition with parallel subtask execution
- Expert skills system (4 built-in skills, Python + MCP tool types)
- Expert portraits (AI-generated SVG)
- Knowledge synthesis and gap awareness
- MCP server with 18+ tools, persistence, security
- CLI observability (--explain, --timeline, --full-trace)
- Auto-fallback on provider failures with circuit breakers
- Cost dashboard with per-expert tracking
- Smart query routing (--auto, --batch) with complexity-based model selection
- Context discovery with semantic search and temporal tracking
- Web dashboard (12 pages) with real-time progress updates and streaming chat
- 3800+ tests

## Near-Term Vision (v2.9-3.0)

### Visible Thinking (Implemented)

Expert reasoning shown in real-time via ThinkingPanel:
- Planning thoughts, tool calls, evidence found, decisions
- Confidence levels per step
- Collapsible panel auto-expands during streaming, summarizes after completion
- `/thinking on/off` toggle, `/trace` for full reasoning chain, `/why` for last decision

### Persistent Memory (Implemented)

Experts remember across sessions:
- Hierarchical memory with conversation episodes
- `/remember` to pin facts, `/forget` to remove, `/memories` to list
- Conversation history browsable and resumable via Conversations API
- Learning history tracked permanently

### Context Compaction (Implemented)

Long sessions stay usable:
- `/compact` summarizes earlier messages while keeping recent context
- Auto-suggest after 30+ messages or 80K+ estimated tokens
- Structured summary preserves key facts, decisions, and open questions

### Graph-Based Knowledge

Replace flat vector search with relationship-aware retrieval:
- Understand connections between concepts
- Traverse knowledge graphs
- Answer "how" and "why" questions better
- Temporal dimension: track *when* findings were discovered, not just what (implemented via `TemporalKnowledgeTracker`)
- Context chaining: output of phase N becomes structured input for phase N+1 (implemented via `ContextChainer`)

### Self-Correction

Detect and fix errors automatically:
- Contradiction detection
- Claim verification
- Confidence decay for outdated info
- Entropy-based stopping (implemented via `EntropyStoppingCriteria`)
- Meta-cognitive evaluation (implemented via `InformationGainTracker`)

## Long-Term Vision (v3.0+)

### Self-Improving Experts

Experts that genuinely evolve:
- Update beliefs when evidence contradicts them
- Track belief provenance over time
- Express honest uncertainty

### Autonomous Research Agent

Systems that identify research needs without prompting:
- Monitor domains for changes
- Prioritize learning based on usage patterns
- Self-assess quality

### Cross-Expert Collaboration (Partial)

Experts that consult each other:
- Expert council implemented: `/council` queries multiple experts in parallel and synthesizes perspectives
- Knowledge transfer between domains via council synthesis
- Collaborative synthesis with agreement/disagreement analysis
- Remaining: persistent cross-expert knowledge sharing, automatic expert-to-expert delegation

## Design Principles

### Quality Over Automation

- Notify, don't auto-inject
- Bias toward over-research
- Transparent by default
- Human judgment for quality, machine execution for scale

### Incremental Autonomy

Build trust before adding autonomy:
1. First: Make reasoning visible
2. Then: Enable self-improvement
3. Never: Sacrifice quality for automation

### Local-First

- User controls their data
- No vendor lock-in
- Best tool for each task

### Secure Autonomy

As agents gain more autonomy (agentic mode, MCP tool access), security becomes critical:
- Defense in depth (sandboxing, verification, permission boundaries)
- Read-only by default, write requires explicit consent
- Cryptographic verification of tool outputs
- Budget enforcement to prevent runaway costs

## What We're Not Building

- General-purpose chat (expert chat is domain-focused; for open-ended conversation, use ChatGPT etc.)
- Real-time responses (deep research takes time)
- Sub-$1 research (comprehensive research costs money)
- Mobile apps
- Complex export formats
- Features that might not work reliably

## The Core Idea

Research is more useful when it builds on itself. Deepr tries to connect research across sessions so each query benefits from prior work.

- Isolated queries produce isolated answers
- Connecting queries produces broader context
- Context chaining links multiple research phases
- Agentic planning sequences research automatically

This is an ongoing effort. Results vary depending on query complexity and document quality.

## Contributing

High-value areas for the vision:
- Context chaining logic
- Synthesis prompts
- Cost optimization
- Knowledge graph integration

Most impactful work is on the intelligence layer, not infrastructure.

## See Also

- [ROADMAP.md](../ROADMAP.md) - What's being built now
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical details
- [EXPERTS.md](EXPERTS.md) - Expert system guide
