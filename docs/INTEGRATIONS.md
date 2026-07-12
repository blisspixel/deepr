# Deepr Integrations

> First-party tool integrations that extend Deepr experts with specialized research instruments.

---

## The Ecosystem Thesis

Deepr, Recon, Distillr, and Primr are four independent tools that each solve one research problem well. Alone, each is useful. Together, they form a compound research system where the whole is greater than the sum of parts.

**What each tool does alone:**

| Tool | Solo value | Install |
|------|-----------|---------|
| **Recon** | Passive domain observations - DNS, email security, and identity indicators | `pip install recon-tool` |
| **Distillr** | Source ingestion - YouTube, websites, arXiv -> structured Markdown corpus | `pip install distillr` |
| **Primr** | Company strategic intelligence - adaptive scraping + AI synthesis -> consultant-grade briefs | `pip install primr` |
| **Deepr** | Multi-provider research automation with persistent expert agents | `pip install -e .` |

**What Deepr adds that none of them have:**

- **Persistent verified memory** - Recon, Distillr, and Primr produce evidence
  artifacts. Deepr can ingest them through explicit verification and graph apply;
  the artifact itself never has belief-write authority.
- **Cross-tool synthesis** - A Deepr expert can combine Recon observations and candidate inferences with a Distillr corpus and Primr briefs without erasing their different evidence status.
- **Gap visibility** - Experts expose missing knowledge and can propose which
  instrument may help. A user or host harness authorizes and executes the call.
- **Traceable handoffs** - Versioned evidence and trace ids can join tool runs,
  but each external tool retains its own spend and credential boundary.
- **Temporal continuity** - Run recon today, primr next week, distillr next month. The expert integrates findings over time and tracks what changed.

**What Deepr does NOT do:**

- Deepr does not replace these tools. It does not re-implement scraping, DNS lookups, or paper ingestion.
- Deepr does not require these tools. Every integration is optional. An expert
  without them still supports stored-state reads and explicit local/plan
  maintenance.
- Deepr does not autonomously orchestrate cross-tool execution in v2.36.
  Experts propose gaps and evidence needs; the user or host harness decides and
  enacts calls under each tool's authority and budget.

---

## Independence Model

Each project must remain fully standalone. No circular dependencies, no import-time coupling.

```
┌─────────────────────────────────────────────────────────┐
│                 Deepr (evidence consumer / role)         │
│  Experts consume structured output from any tool via    │
│  MCP client connections. No direct Python imports.      │
└────────────┬──────────────────┬──────────────────┬──────┘
             │ MCP              │ MCP              │ MCP
             ▼                  ▼                  ▼
      ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
      │    Recon    │   │   Distillr  │   │    Primr    │
      │  (standalone)│   │ (standalone) │   │ (standalone) │
      └─────────────┘   └─────────────┘   └──────┬──────┘
                                                   │ Python import
                                                   ▼ (optional)
                                            ┌─────────────┐
                                            │    Recon    │
                                            │ (DNS pre-   │
                                            │  flight)    │
                                            └─────────────┘
```

**Rules:**

1. **No Python imports between Deepr and sibling tools.** All communication is via MCP (stdio or HTTP). This means any tool can be upgraded, replaced, or removed without breaking the others.
2. **Primr -> Recon is the only direct dependency** (Primr imports recon for its DNS pre-flight). This is fine - it's a lightweight, fast, free call that Primr owns.
3. **Deepr discovers tools at runtime.** If recon isn't installed, the expert skill simply isn't available. No startup errors, no degraded mode - just fewer instruments.
4. **Each tool ships its own MCP server.** Deepr connects as a client. The tool doesn't know or care that Deepr is calling it vs. Claude Desktop vs. Cursor.
5. **Structured output is the contract.** Each tool returns JSON (MCP) or Markdown+YAML (filesystem). Deepr consumes the structure; it never screen-scrapes CLI output.

---

## How They Work Together

### Illustrative Compound Workflow: Company Research

This is an operator- or host-harness-guided sequence, not an autonomous v2.36
Deepr loop. Preview and approve each external tool independently, then submit
its output to Deepr's verification boundary.

```
User asks expert: "What's Stripe's competitive position in embedded finance?"

Expert detects gaps:
  - Domain-scoped infrastructure indicators (what is observable from stripe.com?)
  - Academic context (embedded finance research landscape)
  - Full strategic picture (competitive positioning, hiring signals, initiatives)

Operator or host orchestrates:
  1. Recon -> stripe.com (2s, $0)
     Returns: timestamped DNS and service indicators, collection status,
              provenance, and unresolved explanations
     Expert retains the observations without promoting them to claims about
              what the Stripe organization operates.

  2. Distillr -> papers "embedded finance platform economics"
     Returns: 12 papers ingested, cross-paper synthesis on platform
              economics, network effects, regulatory moats
     Expert absorbs as academic context.

  3. Primr -> stripe.com
     Returns: Full strategic brief - competitive positioning,
              hiring signals (50+ ML roles), API-first architecture,
              regulatory strategy, partnership patterns
     Expert absorbs as strategic knowledge.

  4. Expert consult synthesizes the verified stored evidence through explicit
     local, plan, or separately bounded council capacity
     Output: Integrated analysis with domain observations, explicit inferences, academic
             grounding, and strategic synthesis. Citations trace back
             to DNS records, papers, and primary sources.
```

**Key insight:** No single tool produces this output. Recon gives time-scoped observations and candidate explanations. Distillr gives academic depth. Primr gives strategic synthesis. Deepr can combine them while preserving their provenance and epistemic boundaries.

### Compound Workflow: Sector Mapping

An expert covering a sector (e.g., "AI Infrastructure") can batch across tools:

```
Expert "AI Infrastructure Expert" tasked with sector map:

  1. Recon batch -> [anthropic.com, openai.com, together.ai, anyscale.com, ...]
     Returns: Per-domain infrastructure indicators
     Expert can propose provisional clusters while retaining alternatives and
             avoiding company-wide stack verdicts.

  2. Distillr -> papers "LLM inference optimization" + latest YouTube talks
     Returns: Technical landscape corpus
     Expert absorbs as domain knowledge.

  3. Primr batch -> top 5 companies by signal density
     Returns: Per-company strategic briefs
     Expert synthesizes competitive landscape.

  4. Expert produces: Sector map with infrastructure patterns,
     technical trends, competitive dynamics, and gap analysis
     showing where its knowledge is thin.
```

### Compound Workflow: Technical Due Diligence

For acquisition or partnership evaluation:

```
Expert "M&A Technical Expert" evaluating target company:

  1. Recon -> target.com
     Immediate: What the queried domain exposed at observation time.
     Review leads: email-security posture, CAA absence, identity indicators.
     These are investigation inputs, not proof of organization-wide operation
     or maturity.

  2. Distillr -> target's engineering blog + relevant papers
     Deep: Technical depth, innovation velocity, research contributions.

  3. Primr -> target.com (full mode)
     Strategic: Hiring patterns, competitive positioning, constraints.

  4. Expert synthesizes: Technical due diligence brief with
     infrastructure assessment, technical depth evaluation,
     talent signals, and integration complexity estimate.
```

### Lightweight Workflow: Quick Grounding

Not every workflow needs all three tools. The simplest compound use:

```
Expert researching any company topic:
  1. Recon -> domain (2s, $0) - collect timestamped observations
  2. Expert proceeds with the observation and inference boundary intact

No Distillr or Primr is required. This is evidence anchoring, not automatic
company or product attribution.
```

---

## Integration Tiers

Not all integrations are equal in complexity or value. Ship them in order of effort-to-value ratio:

### Tier 1: Recon (Ship First)

**Why first:** Fast (2-5s), free ($0), stateless, structured JSON output. The simplest possible MCP client integration, with no model spend. Its evidence still needs the inference boundary below.

**What Deepr needs:**
- MCP client connection to `recon mcp` (stdio)
- Auto-approve all tools (they're free and fast)
- Parse JSON response into the versioned evidence handoff before any belief review

**What Recon needs:**
- Accept optional `trace_id` in MCP tool params (pass-through, log it)
- Return `cost: 0.00` field for consistency with other tools

**Expert skill behavior:**
- **Trigger:** Expert encounters a company domain in its research context
- **Action:** Run `domain_lookup`, retain raw observations, then keep any interpretation separate
- **Confidence:** Attach confidence to the exact observation and its collection basis. Do not transfer it to a product-use inference.
- **Retention:** Store time-scoped observations, provenance, collection opportunity, and unresolved candidate explanations

**Effort:** Small. A few hours of wiring on the Deepr side once MCP client basics exist.

### Tier 2: Distillr (Ship Second)

**Why second:** Medium latency (2-10 min), low cost ($0.05-$1), produces the exact artifact format Deepr's corpus import needs (Markdown + YAML frontmatter). Natural bridge between "source material exists" and "expert knows about it."

**What Deepr needs:**
- MCP client connection to `distill-mcp` (stdio)
- Async handling (runs take minutes, need progress)
- Corpus import bridge: read distillr's `library/` output -> feed into expert knowledge
- Budget propagation (cap per-call spend)
- Approval flow for expensive operations (ingest 50 papers = ~$2.50)

**What Distillr needs:**
- Accept `trace_id` in MCP tool params
- Accept `budget` param (cap model spend, fail gracefully if exceeded)
- Return `cost` field in MCP responses (actual spend)
- MCP progress notifications during long ingestion runs
- `query_library` tool for searching existing corpus without new ingestion

**Expert skill behavior:**
- **Trigger:** Expert identifies a knowledge gap that maps to papers, videos, or sites
- **Action:** Call `discover` or `ingest_papers` with gap description as query
- **Approval:** Required if estimated cost > threshold (configurable)
- **Retention:** Absorb synthesis files as permanent knowledge; link to raw corpus for provenance
- **Refresh:** Periodic re-run on same topic to detect new material; integrate delta only

**Effort:** Medium. Async handling and corpus-to-knowledge mapping are the hard parts.

### Tier 3: Primr (Ship Third)

**Why third:** Long latency (35-50 min), moderate cost (~$0.60-$5), produces large structured artifacts. Needs robust async handling, progress notifications, and budget awareness. But the payoff is huge - it replaces the most expensive and time-consuming expert research pattern (company deep dives).

**What Deepr needs:**
- MCP client connection to `primr mcp` (stdio)
- Async durability (35-50 min runs must survive disconnects)
- Progress notifications (phase updates during long runs)
- Budget propagation with pre-flight estimate (`--dry-run` equivalent)
- Approval flow (always, given cost and duration)
- Artifact parsing: Primr's structured output -> expert knowledge sections

**What Primr needs:**
- Accept `trace_id` in MCP tool params
- Accept `budget` param (already has cost controls, wire them to MCP)
- Return `cost` field in MCP responses
- MCP progress notifications per phase (6 phases, each takes minutes)
- Lighter `quick_lookup` tool: recon + scrape only, skip deep research (~5 min, ~$0.10)
- Structured JSON summary alongside full Markdown report (for programmatic consumption)

**Expert skill behavior:**
- **Trigger:** Expert needs strategic context on a specific company
- **Action:** Estimate cost first, request approval, then run full analysis
- **Approval:** Always required (cost + duration)
- **Retention:** Absorb structured sections (competitive positioning, tech stack, hiring signals, strategic initiatives) as company knowledge
- **Refresh:** Re-run periodically; expert integrates delta (what changed since last analysis)

**Effort:** Medium-high. The async durability and progress notification infrastructure is the prerequisite.

---

## Data Flow Contracts

Each tool produces output in a specific shape. Deepr consumes these shapes without transformation where possible.

### Recon -> Deepr

The required Recon boundary is a versioned evidence handoff, not a product-use
verdict. Before Recon output can authorize a structured belief, an adapter must
emit the published
[`deepr-recon-evidence-handoff-v1`](schemas/recon-evidence-handoff-v1.json)
contract. The contract is the interop expectation and frozen-fixture validation
target; it does not claim that every current Recon payload already emits this
shape. It is lossless for the evidence Deepr receives and preserves:

- the exact queried-domain scope and every name for which collection was attempted;
- direct observations separately from candidate inferences;
- the unmodified source payload plus raw observation data, provenance references, and content hashes;
- observation time plus explicit freshness state and basis;
- each collection opportunity, including whether it was attempted and whether it succeeded;
- unresolved alternatives rather than collapsing them into one provider attribution; and
- a separate confidence score and written basis for each observation or inference.

High confidence in a successful DNS observation applies only to that response
for that name at that time. It does not become high confidence that the legal
organization uses or operates a product. An AWS-attributed address, CNAME, or
route can reflect a CDN, hosted dependency, contractor, acquired property,
shared service, or one public edge among several alternatives. A downstream
organization-use belief requires independent evidence and semantic review
outside this handoff.

The contract also distinguishes a successful empty result from a failed or
unattempted collection opportunity. Absence is not evidence when the relevant
collection did not succeed. Removing these distinctions or changing their
meaning requires a new schema version.

Abbreviated handoff view:

```json
{
  "schema_version": "deepr-recon-evidence-handoff-v1",
  "kind": "deepr.integration.recon_evidence_handoff",
  "contract": {
    "lossless_handoff": true,
    "observation_inference_separated": true,
    "organization_product_use_verdict_allowed": false,
    "belief_write_allowed": false
  },
  "source_payload": {
    "media_type": "application/json",
    "raw": {"domain": "stripe.com", "provider": "AWS", "confidence": "high"},
    "content_sha256": "<sha256 of the canonical raw payload>"
  },
  "query_scope": {
    "queried_domain": "stripe.com",
    "queried_names": ["stripe.com"],
    "organization_scope_inferred": false
  },
  "collection": {
    "status": "complete",
    "opportunities": [
      {
        "method": "dns_resolution",
        "target": "stripe.com",
        "attempted": true,
        "succeeded": true
      }
    ]
  },
  "observations": [
    {
      "subject": {"kind": "queried_domain", "value": "stripe.com"},
      "predicate": "dns_resolution_indicator",
      "object": {"provider_indicator": "AWS"},
      "observed_at": "2026-05-07T12:00:00Z",
      "freshness": {"state": "fresh_at_collection", "basis": "DNS TTL"},
      "confidence": {
        "score": 0.99,
        "basis": "successful DNS response",
        "applies_to": "observation"
      }
    }
  ],
  "inferences": [
    {
      "claim_class": "candidate_explanation",
      "status": "unresolved",
      "organization_product_use_verdict": false,
      "eligible_for_belief_write": false,
      "unresolved_alternatives": [
        "The endpoint could be a third-party hosted dependency."
      ]
    }
  ]
}
```

**Admission expectation:** Retain this as replayable domain evidence. For example, "a successful
DNS observation for stripe.com had an AWS-attributed indicator at the observed
time" can remain an observation. "Stripe uses AWS" is an organization-level
inference and is not a verdict authorized by Recon evidence alone. The frozen
[regression fixture](../tests/unit/test_schemas/fixtures/stripe-aws-dns-indicator-v1.json)
captures this boundary.

### Distillr -> Deepr

Distillr produces filesystem artifacts. The MCP `query_library` tool returns metadata; the actual content lives in `library/topics/<topic>/`.

```json
{
  "topic": "embedded_finance",
  "papers_ingested": 12,
  "synthesis_path": "library/topics/embedded_finance/embedded_finance_Paper_Synthesis.md",
  "corpus_synthesis_path": "library/topics/embedded_finance/embedded_finance_Corpus_Synthesis.md",
  "insights_paths": ["library/topics/embedded_finance/papers/..."],
  "cost": 0.82,
  "trace_id": "deepr-trace-abc123"
}
```

**Deepr absorbs as:** The synthesis files become expert knowledge (beliefs with citations). Individual paper insights are available for drill-down but not bulk-loaded into the expert's active memory (too much noise). The expert retains: "I have deep knowledge of embedded finance platform economics from 12 papers (ingested 2026-05-07, synthesis confidence: multi-source)."

### Primr -> Deepr

Primr produces a full strategic report. The MCP tool returns structured metadata + the report path.

```json
{
  "company": "Stripe",
  "domain": "stripe.com",
  "mode": "full",
  "report_path": "output/Stripe_Strategic_Overview_05-07-2026.md",
  "strategy_path": "output/Stripe_AI_Strategy_05-07-2026.md",
  "sections": 23,
  "citations": 48,
  "recon_summary": { "provider": "AWS", "services_count": 14 },
  "hiring_signals": {
    "total_roles": 127,
    "ml_roles": 52,
    "top_initiatives": ["payments infrastructure", "fraud ML", "developer platform"]
  },
  "cost": 0.74,
  "duration_minutes": 38,
  "trace_id": "deepr-trace-abc123"
}
```

**Deepr absorbs as:** Structured company knowledge across multiple belief categories:
- Domain observations and candidate infrastructure interpretations (from the Recon pre-flight embedded in Primr)
- Competitive positioning (from strategic analysis)
- Hiring signals (from job posting analysis)
- Strategic initiatives (from synthesis)
- Constraints and risks (from gap analysis)

Each category gets its own confidence level and timestamp. The expert can later say "my knowledge of Stripe's hiring patterns is from May 2026" and decide whether to refresh.

---

## What Each Project Needs (Checklist)

### Recon (`recon-tool`)

Already done:
- [x] MCP server with stable tool schemas
- [x] `--json` structured output with published schema
- [x] Batch mode with cross-domain clustering
- [x] Delta mode (diff against cached snapshot)

Needed for Deepr integration:
- [ ] Accept optional `trace_id` param in all MCP tools
- [ ] Return `cost: 0.00` field in all MCP responses (consistency)
- [ ] Emit, or let a Deepr adapter wrap output into, `deepr-recon-evidence-handoff-v1`
- [ ] Preserve raw observations, query scope, collection opportunity, time and freshness, provenance, confidence basis, and unresolved alternatives
- [ ] Document MCP tool input/output schemas in a machine-readable format (JSON Schema)

Nice to have:
- [ ] `confidence_scores` per service detection (not just overall confidence)
- [ ] Structured `changes` array in delta output (not just human-readable diff)

### Distillr (`distillr`)

Already done:
- [x] MCP server with 27 live tools verified by Deepr's `$0`
  `tools/list` handshake on 2026-06-25
- [x] Markdown + YAML frontmatter output format
- [x] Cost logging per run
- [x] Free existing-corpus reads: `list_topics`, `find_insights`,
  `read_insight`, `find_concepts`, `read_concept`, `concept_history`,
  `concept_diff`, `research_gaps`, `list_topic_summary`, `okf_validate`,
  `costs`, and `doctor`
- [x] Approval-gated corpus synthesis or writes: `ask`,
  `find_insights_summary`, `okf_export`, `synthesize`,
  `resynthesize_topic`, and `generate_report`
- [x] Approval-gated ingestion and refresh: `discover`, `papers`,
  `learn_topic`, `process_video_url`, `search_videos`, `site_batch`, and
  `catch_up`
- [x] Watch-list mutation tools: `watch_add` and `watch_remove`

Needed for Deepr integration:
- [ ] Accept `trace_id` param in all MCP tools
- [ ] Accept `budget` param (cap model spend per call)
- [ ] Return `cost` field in MCP tool responses (not just log file)
- [ ] MCP progress notifications during ingestion (per-paper/per-video progress)
- [ ] Structured summary response from ingestion tools (not just filesystem paths)
  - Include: topic, count ingested, synthesis path, key findings preview, cost

Nice to have:
- [x] `catch_up` tool: re-run on existing topic and integrate new material
- [ ] `estimate` tool: preview cost before ingestion (like `--preview` but via MCP)
- [ ] Add last-updated timestamps to `list_topics` corpus metadata
- [ ] Explicit zero-cost metadata on `ask` and `find_insights_summary` if they
  are guaranteed not to call a model. Until then, Deepr keeps them
  approval-gated.

### Primr (`primr`)

Already done:
- [x] MCP server (8 tools, 4 resources, 2 prompts)
- [x] Structured artifact output (MD, TXT, DOCX)
- [x] Cost estimation (`--dry-run`)
- [x] Job management (async, check status, cancel)
- [x] Recon integration (DNS pre-flight built in)
- [x] Strategy types extensible via YAML
- [x] Budget controls and governance hooks

Needed for Deepr integration:
- [ ] Accept `trace_id` param in all MCP tools
- [ ] Return `cost` field in MCP tool responses (actual spend)
- [ ] MCP progress notifications per phase (6 phases × status updates)
- [ ] Structured JSON summary alongside Markdown report
  - Include: company metadata, key findings by category, hiring signals summary, recon summary, citations count, confidence levels
- [ ] `quick_lookup` MCP tool: recon + scrape only, no deep research (~5 min, ~$0.10)
  - For when the expert needs fast context, not a full 40-min analysis

Nice to have:
- [ ] `delta` tool: re-run on previously analyzed company, return what changed
- [ ] Structured `hiring_signals` as standalone MCP tool (fast, focused)
- [ ] Accept `sections` param to request only specific report sections

---

## Deepr-Side Implementation

### MCP Client Profile System

Deepr needs a general MCP client profile system (Phase 2). First-party integrations are the first consumers of that system, but the system itself is generic - it works with any MCP server.

```yaml
# ~/.deepr/integrations.yaml
integrations:
  recon:
    command: "recon mcp"
    transport: stdio
    enabled: true
    budget_propagation: false
    auto_approve: [domain_lookup, batch_lookup, delta]
    timeout: 30s

  distillr:
    command: "distill-mcp"
    transport: stdio
    enabled: true
    budget_propagation: true
    max_budget_per_call: 2.00
    auto_approve: [query_library]
    require_approval: [ingest_papers, ingest_youtube, ingest_sites, discover]
    timeout: 15m
    progress: true

  primr:
    command: "primr-mcp --stdio"
    transport: stdio
    enabled: true
    budget_propagation: true
    max_budget_per_call: 5.00
    require_approval: [research_company, generate_strategy, batch_analyze]
    auto_approve: [estimate_run, check_jobs, doctor]
    timeout: 60m
    progress: true
```

**Key design decisions:**

- `enabled: true/false` - Tools are opt-in. If not installed or not configured, they simply don't appear as available instruments.
- `auto_approve` vs `require_approval` - Free/fast tools auto-approve. Expensive/slow tools require human or expert-level approval.
- `budget_propagation` - Deepr's per-operation budget flows through. If the expert has $3 remaining and primr estimates $0.60, it proceeds. If it estimates $5, it stops.
- `timeout` - Appropriate per tool. Recon: 30s. Distillr: 15m. Primr: 60m.
- `progress: true` - Subscribe to MCP progress notifications for long-running tools.

### Expert Skill Wrappers

Each integration gets a thin skill wrapper that defines *when* and *how* an expert uses the tool:

```yaml
# Example: recon skill definition
skill:
  name: "domain-intelligence"
  tool: recon
  version: "1.0"

triggers:
  - type: domain_mention
    pattern: "\\b[a-z0-9-]+\\.(com|io|ai|org|net|co)\\b"
    action: suggest  # suggest to expert, don't auto-run

  - type: gap_detected
    categories: ["infrastructure", "tech_stack", "cloud_platform"]
    action: auto_run  # run automatically for infrastructure gaps

behavior:
  pre_research: true  # run before LLM research, not after
  confidence: source_scoped  # observation confidence does not transfer to inference
  retention: structured_evidence  # keep observations, candidates, and provenance distinct
  refresh_policy: 30d  # re-run if data older than 30 days
```

### Knowledge Absorption Pipeline

When a tool returns results, the expert needs to *absorb* them - not just store them, but integrate them into its belief system:

1. **Parse** - Extract structured data from tool response
2. **Categorize** - Map findings to expert knowledge categories (infrastructure, competitive, academic, strategic)
3. **Confidence-tag** - Score the exact observation or inference and record its basis. Source confidence never transfers automatically to a broader claim.
4. **Deduplicate** - Check if expert already knows this (avoid redundant beliefs)
5. **Integrate** - Update existing beliefs or add new ones with provenance
6. **Gap-check** - After absorption, re-evaluate gap backlog (some gaps may now be filled)

This pipeline is the same regardless of which tool produced the data. The tool-specific part is only the parsing step.

---

## Cross-Project Coordination

### Shared Conventions

All four projects (Deepr, Recon, Distillr, Primr) should follow:

1. **MCP tool naming:** `verb_noun` format (e.g., `domain_lookup`, `ingest_papers`, `research_company`)
2. **Response envelope:** Every MCP response includes `{ cost, trace_id, duration_ms, ...payload }`
3. **Error format:** `{ error: true, category: "budget_exceeded"|"timeout"|"not_found"|..., message: "...", retryable: bool }`
4. **Budget param:** Tools that spend money accept `budget: float` and refuse to exceed it
5. **Trace ID:** All tools accept optional `trace_id: string` and echo it back (enables cross-tool tracing in Deepr's observability layer)

### Version Compatibility

- Deepr targets the *current stable* version of each sibling tool
- Breaking MCP schema changes in sibling tools require a major version bump
- Deepr's integration config includes `min_version` per tool
- If a tool is installed but below min_version, Deepr warns but doesn't crash

### Testing Strategy

- **Unit tests in Deepr:** Mock MCP responses from each tool, test absorption pipeline
- **Integration tests:** Explicit opt-in only, with each external tool installed,
  its cost estimated, and its own authorization present. CI uses frozen fixtures.
- **Contract tests:** Each sibling repo includes a test that validates its MCP output against the shared schema (catches drift before it reaches Deepr)

---

## What This Unlocks (The Compound Value)

Individual tools are useful. The compound system is qualitatively different:

| Capability | Recon alone | Distillr alone | Primr alone | Deepr + all three |
|-----------|-------------|----------------|-------------|-------------------|
| Company tech stack | yes (one-shot) | - | yes (embedded) | yes (persistent, tracked over time) |
| Academic depth | - | yes (one-shot corpus) | - | yes (absorbed into expert memory, cross-referenced with company data) |
| Strategic analysis | - | - | yes (one-shot report) | yes (persistent, updated, synthesized across companies) |
| Cross-source synthesis | - | - | - | yes, after explicit verified ingestion |
| Temporal tracking | - | - | - | yes, from durable observation and belief events |
| Gap proposals | - | - | - | yes; execution remains user or host authorized |
| Cross-tool budget | - | - | - | no single shared external-tool budget in v2.36 |
| Audit trail | - | - | - | Deepr traces its own handoffs; external tools retain their own logs |

The compound value is durable, provenance-preserving expert state over explicit
tool handoffs. Autonomous cross-tool execution and one shared budget remain
future work, not shipped v2.36 behavior.

---

## Links

- [Recon](https://github.com/blisspixel/recon) - Passive domain intelligence
- [Distillr](https://github.com/blisspixel/distillr) - Source ingestion engine
- [Primr](https://github.com/blisspixel/primr) - Strategic company intelligence
- [Deepr Roadmap - Phase 2](../ROADMAP.md) - MCP client infrastructure
- [Deepr Roadmap - Phase 2b](../ROADMAP.md) - First-party integrations
- [Deepr Roadmap - Phase 4](../ROADMAP.md) - Expert skills and corpus import
