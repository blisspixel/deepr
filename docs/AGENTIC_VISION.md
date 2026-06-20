# Deepr Agentic Vision - May 2026 and Beyond

> How Deepr becomes dramatically more agentic while simultaneously being the best research role on any agent team.

---

## The Two-Sided Opportunity

Deepr has a unique position in the agentic ecosystem. It needs to be excellent at **two things simultaneously**:

1. **Being agentic internally** - Experts that truly reason, plan, reflect, self-correct, and learn autonomously
2. **Playing well on agent teams** - Being the best possible research role that other agents can call via MCP and A2A

These aren't in tension. The more genuinely agentic Deepr experts become internally, the more valuable they are as team members on external agent workflows. A research expert that can plan multi-step investigations, reflect on its own gaps, and self-correct its conclusions is dramatically more useful than one that just wraps an LLM call.

---

## Where Deepr Stands Today vs. State of the Art

### What "truly agentic" means in 2026

Based on current research and production patterns, an agentic system in 2026 has these capabilities:

| Capability | State of the Art | Deepr Today | Gap |
|-----------|-----------------|-------------|-----|
| **Planning** - decompose goals into steps | Multi-step planning with replanning on failure | Expert task planning exists but is chat-driven | Experts should autonomously plan research campaigns |
| **Reflection** - critique own output, self-correct | Generate → critique → revise loops (20% accuracy improvement) | QA exists but is manual/external | Experts should self-evaluate research quality before delivering |
| **Memory** - persistent, structured, cross-session | Graph-based knowledge networks, Zettelkasten-style linking, temporal awareness | Belief states + gap tracking (good foundation) | Need graph-structured memory with temporal decay and confidence evolution |
| **Tool use** - dynamic selection based on state | Agents choose tools based on current context, not hardcoded sequences | Skills with auto-triggers (good) | Need dynamic tool selection based on gap analysis, not just pattern matching |
| **Multi-agent coordination** - handoffs, delegation | A2A protocol, structured task delegation with opaque internals | MCP server (good), but no A2A, no structured handoff protocol | Need A2A support + structured task/artifact contracts |
| **Guardrails** - layered safety, budget, scope | Input/output guardrails, tool risk ratings, human-in-the-loop | Budget enforcement (excellent), approval flows (good) | Need output quality guardrails and scope-drift detection |
| **Autonomy with bounds** - run until done, within constraints | Continuous execution with exit conditions and escalation | Agentic chat exists but is session-bound | Need long-running autonomous research campaigns that survive sessions |

### What Deepr already does well (keep and amplify)

- **Budgeted autonomy** - This is ahead of the curve. Most agent frameworks are just now adding budget controls. Deepr has multi-layer budget protection, cost ledgers, and per-operation limits. This is a competitive advantage.
- **Decision records** - Structured audit trails of routing choices, source trust decisions. This maps directly to the "observability" requirement in enterprise agentic systems.
- **Expert persistence** - Belief states, gap tracking, knowledge accumulation. This is the foundation of agentic memory. Most frameworks are still stateless.
- **Provider portability** - Multi-provider routing with fallback. This is exactly what production agentic systems need.

---

## Concrete Improvements: Making Deepr Dramatically More Agentic

### 1. Reflection and Self-Correction Loop

**The gap:** Experts produce research but don't evaluate their own output quality before delivering it. They don't ask "is this actually good enough?"

**The fix:** Add a reflection step to the expert research pipeline:

```
Expert receives question →
  1. Plan research approach (what sources, what tools, what budget)
  2. Execute research (current behavior)
  3. REFLECT: Evaluate own output against criteria:
     - Are claims grounded in citations?
     - Are there logical gaps or contradictions?
     - Is confidence calibrated (not over/under-confident)?
     - Are there obvious follow-up questions left unanswered?
  4. If reflection identifies issues → self-correct and re-research specific gaps
  5. Deliver with reflection metadata (what was revised, why)
```

**Why it matters:** Research that's been self-critiqued is dramatically more trustworthy. The reflection step catches hallucinations, unsupported claims, and logical gaps before they reach the user or downstream agent.

**Implementation:** Use a separate model call (can be cheaper model) as the "critic" that evaluates the research output against a rubric. If the critic identifies issues above a threshold, trigger targeted re-research on the specific gaps.

### 2. Autonomous Research Campaigns (Long-Running Agents)

**The gap:** Experts are session-bound. You chat with them, they research, you leave. They can't run multi-day research campaigns autonomously.

**The fix:** Research campaigns that survive sessions:

```bash
# Launch a campaign - expert works autonomously over hours/days
deepr expert campaign "AI Strategy Expert" \
  --goal "Map the competitive landscape of AI inference providers" \
  --budget 15 \
  --duration 7d \
  --checkpoint daily

# Expert autonomously:
#   - Plans research phases
#   - Executes research across providers
#   - Fills gaps it discovers
#   - Produces daily checkpoint summaries
#   - Delivers final synthesis when complete or budget exhausted
```

**Why it matters:** Real research isn't a single question. It's a multi-day investigation with branching paths, dead ends, and iterative refinement. An expert that can run autonomously for days - within budget bounds - is qualitatively different from one that only responds to prompts.

**Implementation:**
- Campaign definition: goal, budget, duration, checkpoint frequency, stop conditions
- Campaign executor: runs in background (queue-based), persists state to disk
- Checkpoint system: periodic summaries of progress, spend, gaps remaining
- Human-in-the-loop: configurable approval gates at budget thresholds or before high-cost operations
- Resume/pause: campaigns survive process restarts

### 3. Graph-Structured Expert Memory

**The gap:** Expert knowledge is stored as flat beliefs. There's no structure showing how beliefs relate to each other, how they were derived, or how they evolve over time.

**The fix:** Evolve expert memory from flat beliefs to a knowledge graph:

```
Current: beliefs = [
  {claim: "Stripe uses AWS", confidence: high, source: recon, date: 2026-05-07},
  {claim: "Stripe has 50+ ML roles", confidence: medium, source: primr, date: 2026-05-07},
]

Future: knowledge_graph = {
  nodes: [
    {id: "stripe-infra", type: "fact", claim: "Stripe uses AWS", ...},
    {id: "stripe-ml-hiring", type: "signal", claim: "50+ ML roles", ...},
    {id: "stripe-ml-investment", type: "inference", claim: "Heavy ML investment", ...},
  ],
  edges: [
    {from: "stripe-ml-hiring", to: "stripe-ml-investment", type: "supports"},
    {from: "stripe-infra", to: "stripe-ml-investment", type: "enables"},
  ],
  temporal: [
    {node: "stripe-ml-hiring", observed: "2026-05-07", confidence_trajectory: [0.7, 0.8, 0.85]},
  ]
}
```

**Why it matters:** Graph memory enables:
- **Inference chains** - Expert can explain *why* it believes something (trace back through supporting evidence)
- **Contradiction detection** - When new evidence conflicts with existing beliefs, the graph shows exactly what's in tension
- **Temporal awareness** - Expert knows which knowledge is fresh vs. stale and can prioritize refresh
- **Gap detection** - Disconnected subgraphs reveal knowledge areas that lack supporting evidence

**Implementation:** Start with a lightweight in-memory graph (networkx or similar) persisted as JSON. Don't over-engineer - the value is in the *structure*, not the database technology. Evolve to a proper graph DB only if scale demands it.

### 4. Dynamic Tool Selection via Gap Analysis

**The gap:** Expert skills trigger on pattern matching (e.g., "domain mentioned" → run recon). This is reactive, not strategic.

**The fix:** Experts should select tools based on gap analysis:

```
Expert analyzing its knowledge state:
  "I have strong competitive positioning data for Stripe (from primr, 2 weeks ago)
   but my infrastructure knowledge is stale (recon, 3 months ago)
   and I have no academic grounding on payment platform economics."

Expert decides:
  1. Run recon refresh on stripe.com (free, 2s) - update infrastructure facts
  2. Skip primr (recent enough, budget-conscious)
  3. Trigger distillr for papers on "payment platform network effects" (fill academic gap)
```

**Why it matters:** This is the difference between a tool that runs when triggered and an agent that *reasons about what it needs*. The expert becomes a strategic planner of its own knowledge acquisition.

**Implementation:** Gap analysis already exists. The addition is a "tool recommendation engine" that maps gap categories to available tools and estimates the value/cost of filling each gap. The expert then prioritizes based on the current question + budget.

### 5. A2A Protocol Support (Agent-to-Agent)

**Current status:** Deepr exposes MCP tools (agent-to-tool) and now has a
baseline A2A server for agent-to-agent task exchange. The remaining gap is
higher-value A2A skill coverage: multi-expert councils, campaign tasks, and
fully backed streaming execution for long research work.

**The fix:** Deepr experts should be discoverable and callable via A2A:

```json
// /.well-known/agent.json - A2A Agent Card
{
  "name": "Deepr AI Strategy Expert",
  "description": "Persistent domain expert specializing in AI industry competitive dynamics",
  "url": "https://localhost:9000",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "skills": [
    {
      "id": "company-research",
      "name": "Company Strategic Research",
      "description": "Deep strategic analysis of a company including competitive positioning, tech stack, hiring signals",
      "inputModes": ["text/plain", "application/json"],
      "outputModes": ["text/plain", "application/json", "text/markdown"]
    },
    {
      "id": "sector-mapping",
      "name": "Sector Landscape Mapping",
      "description": "Map competitive landscape across multiple companies in a sector",
      "inputModes": ["text/plain", "application/json"],
      "outputModes": ["application/json", "text/markdown"]
    }
  ]
}
```

**Why it matters:** A2A is gaining rapid adoption (150+ organizations, Linux Foundation governance). It's complementary to MCP:
- **MCP** = how an agent connects to tools (Deepr already does this)
- **A2A** = how agents talk to each other as peers (Deepr needs this)

With A2A, a planning agent can discover Deepr experts, send them structured tasks, receive streaming progress updates, and get structured results - all without knowing Deepr's internals. This makes Deepr experts first-class citizens on any A2A-compatible agent team.

**Implementation status:** The baseline is shipped:
- `deepr a2a` command to start A2A server
- Agent Card at `/.well-known/agent.json` describing expert capabilities
- Task lifecycle: submitted to working to completed/failed/cancelled
- Budget propagation via task metadata
- Versioned `deepr-a2a-task-v1` task/result envelope with runtime
  fail-closed validation

Remaining: streaming updates backed by real long-running expert work,
multi-expert council skills, and campaign-oriented A2A tasks.

### 6. Structured Handoff Contracts

**The gap:** When a Deepr expert produces output for a downstream agent, the format is ad-hoc. There's no formal contract for what the handoff artifact contains.

**The fix:** Define explicit handoff schemas that downstream agents can rely on:

```json
// Deepr expert handoff artifact
{
  "schema_version": "1.0",
  "expert": "AI Strategy Expert",
  "task_id": "task-abc123",
  "trace_id": "trace-xyz789",
  "produced_at": "2026-05-07T14:30:00Z",
  "confidence": 0.82,
  "budget_spent": 1.45,
  
  "findings": {
    "summary": "...",
    "key_claims": [
      {
        "claim": "Stripe is investing heavily in ML-based fraud detection",
        "confidence": 0.85,
        "evidence_type": "hiring_signals + public_statements",
        "citations": ["https://...", "https://..."],
        "staleness": "2_weeks"
      }
    ],
    "knowledge_gaps": ["No data on Stripe's inference infrastructure costs"],
    "contradictions": []
  },
  
  "metadata": {
    "sources_consulted": 14,
    "tools_used": ["recon", "primr", "deepr_research"],
    "reflection_passes": 2,
    "quality_score": 0.88
  }
}
```

**Why it matters:** Downstream agents need to know:
- How confident is this research?
- What's the provenance of each claim?
- What gaps remain?
- How fresh is the data?

Without structured handoffs, downstream agents treat Deepr output as opaque text. With them, they can make informed decisions about whether to trust, verify, or request more research.

### 7. Expert-as-Guardrail Pattern

**The gap:** Deepr experts are only used for research. But their accumulated knowledge makes them excellent *validators* for other agents' work.

**The fix:** Experts can serve as guardrails/validators for other agents:

```
Downstream coding agent about to deploy infrastructure change →
  Calls Deepr "Cloud Security Expert" as a guardrail:
    "Validate this Terraform plan against known security best practices
     and the target company's compliance requirements"
  
  Expert responds with:
    - PASS/WARN/FAIL assessment
    - Specific concerns with citations
    - Confidence level
    - Knowledge gaps that limit the assessment
```

**Why it matters:** This is a new *consumption pattern* for Deepr experts. They're not just research tools - they're domain validators. This dramatically expands the surface area where Deepr adds value in agent workflows.

**Implementation:** Add a `validate` mode to expert MCP/A2A tools alongside the existing `research` and `chat` modes. The expert applies its accumulated knowledge as a filter/validator rather than a generator.

### 8. Skill Portability (agentskills.io + OpenClaw)

**The gap:** Deepr expert skills are Deepr-specific. They can't be used by other agent platforms without custom integration.

**The fix:** Package Deepr expert capabilities as portable skills following the agentskills.io open standard:

```markdown
# SKILL.md - Deepr Research Expert Skill
---
name: deepr-research
description: Deep multi-provider research with persistent expert memory
version: 2.10.0
mcp_server: deepr-mcp
tools:
  - research_query
  - expert_consult
  - expert_validate
triggers:
  - pattern: "research|investigate|analyze|what do we know about"
    action: activate
---

## Instructions
You have access to Deepr research experts via MCP. Use them when...
```

**Why it matters:** The agentskills.io standard is gaining traction across Claude Code, Kiro, Cursor, and other agent platforms. Packaging Deepr as a portable skill means it works everywhere without per-platform integration work. Primr already does this (`claude-code/skills/primr/SKILL.md`).

---

## How Deepr Provides Skills/MCP to Other Platforms

### Current State
- Full MCP tool suite (functional, well-tested; see [mcp/README](../mcp/README.md))
- Works with Claude Desktop, Cursor, VS Code

### What to Add

**1. Richer MCP Resources (not just tools)**

MCP has four capability types: Tools, Resources, Prompts, and Sampling. Deepr currently only exposes Tools. Adding Resources and Prompts makes Deepr much more useful:

```
Resources (read-only data the host can pull):
  deepr://experts/list              → all available experts
  deepr://experts/{name}/knowledge  → expert's current knowledge state
  deepr://experts/{name}/gaps       → expert's gap backlog
  deepr://research/recent           → recent research results
  deepr://costs/summary             → current budget status

Prompts (reusable prompt templates):
  deepr://prompts/research-workflow  → guided research workflow
  deepr://prompts/expert-consult    → how to consult an expert effectively
  deepr://prompts/sector-analysis   → sector mapping workflow
```

**2. MCP Sampling (reverse direction)**

MCP Sampling lets servers request LLM completions from the client. This is powerful for Deepr because:
- Deepr can ask the *host's* model to help with synthesis (using the host's context window)
- Enables collaborative research where Deepr provides facts and the host model provides reasoning
- No additional API keys needed on Deepr's side for this path

**3. Streaming and Progress**

Long research operations (especially with primr/distillr) need streaming progress:
- Phase updates during multi-step research
- Partial results as they become available
- Budget consumption updates in real-time
- Estimated time remaining

**4. Multi-Expert Coordination via MCP**

Expose expert council as a single MCP tool that coordinates multiple experts:

```json
{
  "tool": "expert_council",
  "params": {
    "question": "Should we build or buy an ML inference platform?",
    "experts": ["AI Strategy Expert", "Cloud Infrastructure Expert", "Cost Optimization Expert"],
    "budget": 5.00,
    "output_format": "structured_debate"
  }
}
```

---

## Roadmap Integration

These improvements are now part of the [Deepr Roadmap](../ROADMAP.md):

**Phase 2 (MCP Client Reliability + Agent Interoperability):**
- A2A server support (`deepr a2a` command with Agent Card)
- MCP Resources and Prompts (not just Tools)
- MCP Sampling support (server requests completions from client)
- Streaming progress for long-running operations
- Skill portability via agentskills.io

**Phase 4 (Expert Intelligence and Quality Loop):**
- Reflection loop: experts self-evaluate before delivering research
- Graph-structured expert memory (knowledge graph with temporal awareness)
- Dynamic tool selection via gap analysis (strategic, not reactive)
- Expert-as-guardrail mode (validate, not just research)

**Phase 4b (Autonomous Research Campaigns):**
- Campaign definition: goal, budget, duration, checkpoints, stop conditions
- Background campaign executor (queue-based, survives sessions)
- Checkpoint system with daily/weekly summaries
- Human-in-the-loop approval gates at configurable thresholds
- Campaign resume/pause/cancel
- Multi-expert campaigns (council works on a shared goal over time)

**Phase 5 (Operations, Team, and Security Hardening):**
- Structured handoff contracts (versioned JSON schemas for expert output)
- OpenClaw integration (governed workflows with estimate/approve/execute)
- A2A discovery: experts advertise capabilities to agent networks

---

## The Compound Effect

When all of this lands, Deepr experts become:

1. **Self-improving** - They reflect on their own output, catch errors, and self-correct
2. **Autonomous** - They run multi-day research campaigns within budget bounds
3. **Structured** - Their knowledge is a graph with provenance, not a flat list
4. **Strategic** - They choose tools based on gap analysis, not pattern matching
5. **Interoperable** - They speak MCP (tools), A2A (agent-to-agent), and agentskills.io (portable skills)
6. **Composable** - They serve as researchers, validators, and council members on any agent team
7. **Auditable** - Every decision, tool call, reflection pass, and handoff is traced

This is what "truly agentic" means for a research system: not just "it calls LLMs" but "it reasons about what it knows, what it doesn't know, how to fill the gaps, and whether its output is good enough."

---

## References

- [OpenAI: A Practical Guide to Building Agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/) - Agent design foundations, orchestration patterns, guardrails
- [A2A Protocol](https://a2a-protocol.org/latest/) - Agent-to-Agent communication standard (Linux Foundation)
- [MCP Specification](https://modelcontextprotocol.io/specification/) - Tools, Resources, Prompts, Sampling, Elicitation
- [agentskills.io](https://agentskills.io/) - Portable agent skill standard
- [Agentic Memory for LLM Agents (arXiv:2502.12110)](https://arxiv.org/abs/2502.12110) - Zettelkasten-inspired dynamic memory organization
- [Agentic RAG Survey (arXiv:2501.09136)](https://arxiv.org/abs/2501.09136) - Reflection, planning, corrective retrieval patterns
