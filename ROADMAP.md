# Deepr Development Roadmap

> **Note**: Model and pricing information current as of January 31, 2026. AI evolves rapidly - verify at provider websites.

## Quick Links

- [Model Selection Guide](docs/MODELS.md) - Provider comparison, costs, when to use what
- [Expert System Guide](docs/EXPERTS.md) - Creating and using domain experts
- [Vision & Future](docs/VISION.md) - Aspirational features (v3.0+)
- [Architecture](docs/ARCHITECTURE.md) - Technical details, security, observability

---

## Current Status (v2.5)

### What Works

- Multi-provider support (OpenAI GPT-5.2, Gemini, Grok 4, Azure)
- Deep Research via OpenAI API (o3/o4-mini-deep-research)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning
- Agentic expert chat (experts can trigger research)
- Knowledge synthesis and gap awareness
- MCP server for AI agent integration
- Multi-layer budget protection
- CLI and Web UI

### Recent Completions

- [x] Semantic command interface
- [x] Expert system foundation (create, chat, learn)
- [x] Autonomous learning with curriculum generation
- [x] Agentic research in expert chat
- [x] MCP Advanced Patterns (Dynamic Tool Discovery, Subscriptions, Elicitation)
- [x] Budget protection with pause/resume
- [x] 302+ tests passing

---

## Active Priorities

### Priority 1: UX Polish (DONE)

- [x] Cross-platform path handling
- [x] Progress feedback during operations
- [x] `deepr doctor` diagnostics
- [x] Stale job status refresh
- [x] Consistent command patterns

### Priority 2: Semantic Commands (DONE)

Intent-based commands that express what you want:

```bash
deepr research "Topic"           # Auto-detects mode
deepr learn "Topic" --phases 3   # Multi-phase learning
deepr team "Decision question"   # Multi-perspective analysis
deepr check "Claim to verify"    # Fact verification
deepr make docs --files *.py     # Generate documentation
deepr make strategy "Goal"       # Strategic analysis
```

### Priority 2.5: Expert System (DONE)

Domain experts that learn and improve:

```bash
deepr expert make "Name" --files docs/*.md --learn --budget 10
deepr expert chat "Name" --agentic --budget 5
deepr expert fill-gaps "Name" --budget 5
```

See [docs/EXPERTS.md](docs/EXPERTS.md) for full guide.

### Priority 3: MCP Integration (DONE)

AI agents can use Deepr via Model Context Protocol:

- `deepr_research` - Submit research jobs
- `deepr_query_expert` - Query domain experts
- `deepr_agentic_research` - Multi-step workflows
- Dynamic tool discovery (85% context reduction)
- Resource subscriptions (70% token savings vs polling)
- Human-in-the-loop for budget decisions

See [mcp/README.md](mcp/README.md) for setup.

### Priority 4: Observability (IN PROGRESS)

- [ ] Auto-generated metadata for all tasks
- [ ] `--explain`, `--timeline`, `--full-trace` flags
- [ ] Cost attribution dashboard
- [ ] Decision logs in natural language

### Priority 5: Provider Routing (TODO)

- [ ] Real-time performance benchmarking
- [ ] Auto-fallback on provider failures
- [ ] Continuous optimization based on metrics

### Priority 6: Context Discovery (TODO)

- [ ] Detect related prior research
- [ ] Notify-only (never auto-inject)
- [ ] Explicit reuse with warnings

### Priority 7: NVIDIA Provider (LATER)

Support for self-hosted NVIDIA NIM infrastructure. Only for enterprises with existing NVIDIA deployments.

---

## Build Order

Current focus areas in priority order:

1. **Observability** - Make reasoning visible
2. **Provider routing** - Auto-optimize model selection
3. **Visible thinking** - Show expert reasoning in real-time
4. **Persistent memory** - Experts remember across sessions

---

## Model Strategy

**Dual approach: Deep Research + Fast Models**

| Use Case | Model | Cost | When |
|----------|-------|------|------|
| Deep Research | o4-mini-deep-research | $0.50-2.00 | Complex analysis (~20%) |
| Planning | GPT-5.2 | $0.20-0.30 | Curriculum, synthesis |
| Quick ops | Grok 4 Fast | $0.01 | Lookups, chat (~80%) |
| Large docs | Gemini 3 Pro | $0.15 | 1M token context |

Using fast models for 80% of operations reduces costs by ~90%.

See [docs/MODELS.md](docs/MODELS.md) for full guide.

---

## Budget Protection

Multi-layer controls prevent runaway costs:

**Hard Limits:**
- Per operation: $10 max
- Per day: $50 max
- Per month: $500 max

**Features:**
- Session budgets with alerts at 50%, 80%, 95%
- Circuit breaker after repeated failures
- Pause/resume for long-running operations
- CLI validation for high budgets

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#cost-safety) for details.

---

## Non-Goals

Not building:
- Chat interface (use ChatGPT)
- Real-time responses (deep research takes minutes)
- Sub-$1 research (comprehensive research costs money)
- Mobile apps
- Complex export formats
- Features that might not work reliably

---

## Philosophy

Every feature should:
- Support long-running research workflows
- Build context across phases
- Synthesize from multiple sources
- Work across providers

Focus on intelligence layer (planning, synthesis, routing), not infrastructure.

---

## Contributing

High-value areas:
- Context chaining logic
- Synthesis prompts
- Cost optimization
- Provider integrations

Most impactful work is on intelligence layer.

---

## Dogfooding

We use Deepr to build Deepr:
- Research implementation questions
- Get comprehensive answers with citations
- Implement based on findings
- Document the research

Example: "Research best practices for context injection in multi-step LLM workflows"
- Cost: $0.17
- Result: 15KB report with citations
- Impact: Validated ContextBuilder design

---

## Future Vision

See [docs/VISION.md](docs/VISION.md) for aspirational features:
- Visible thinking (show reasoning)
- Persistent memory (remember across sessions)
- Graph-based knowledge (relationship-aware retrieval)
- Self-improving experts
- Expert councils

---

## Code Quality

### Completed
- [x] Custom exception hierarchy (`deepr/core/errors.py`)
- [x] Embedding cache for search optimization
- [x] Test organization cleanup
- [x] Performance documentation
- [x] Security documentation

### TODO
- [ ] ExpertProfile refactoring (split responsibilities)
- [ ] Configuration consolidation (single source of truth)
- [ ] Richer belief revision (experts update views over time)

---

## Version History

| Version | Focus | Status |
|---------|-------|--------|
| v2.0 | Core infrastructure | Complete |
| v2.1 | Adaptive research workflow | Complete |
| v2.2 | Semantic commands | Complete |
| v2.3 | Expert system | Complete |
| v2.4 | MCP integration | Complete |
| v2.5 | Agentic experts | Complete |
| v2.6 | Observability | In Progress |
| v3.0+ | Self-improvement | Future |

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
