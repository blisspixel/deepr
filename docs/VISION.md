# Deepr Vision

> **Note**: This document describes aspirational goals, not current capabilities. See [ROADMAP.md](../ROADMAP.md) for what's actually implemented.

## The Goal

Transform research from isolated queries into cumulative understanding. Build systems that learn and improve over time.

## Current State (v2.6)

What works today:
- Multi-provider deep research (OpenAI, Gemini, Grok, Azure)
- Gemini Deep Research Agent via Interactions API
- Multi-phase research with context chaining
- Domain experts from documents with autonomous learning
- Agentic research (experts can trigger research)
- Knowledge synthesis and gap awareness
- MCP server with 10 tools, persistence, security
- CLI observability (--explain, --timeline, --full-trace)
- Auto-fallback on provider failures
- Cost dashboard with per-expert tracking

## Near-Term Vision (v2.7-2.9)

### Visible Thinking

Show expert reasoning in real-time:
- Planning thoughts
- Decision rationale
- Confidence levels
- Trade-off analysis

Goal: Build trust through transparency.

### Persistent Memory

Experts that remember across sessions:
- User preferences and context
- Conversation patterns
- Learning history

### Graph-Based Knowledge

Replace flat vector search with relationship-aware retrieval:
- Understand connections between concepts
- Traverse knowledge graphs
- Answer "how" and "why" questions better
- Temporal dimension: track *when* findings were discovered, not just what
- Context chaining: output of phase N becomes structured input for phase N+1

### Self-Correction

Detect and fix errors automatically:
- Contradiction detection
- Claim verification
- Confidence decay for outdated info
- Entropy-based stopping (detect when searches yield diminishing returns)
- Meta-cognitive evaluation ("Did this search yield new information or just confirm priors?")

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

### Cross-Expert Collaboration

Experts that consult each other:
- Knowledge transfer between domains
- Collaborative synthesis
- Expert councils for complex decisions

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

- Chat interface (use regular ChatGPT)
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
