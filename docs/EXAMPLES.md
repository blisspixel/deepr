# Deepr Scenario Catalog

These examples illustrate useful research scenarios. They are not the current
command contract. In v2.36, direct bounded single-job research works only when
preview can prove a complete finite envelope. Metered `learn`, `team`, expert
chat, nonlocal expert `--learn`, hosted `--upload`, vector stores, campaigns,
and legacy artifact generation are gated before provider work. Use
[Supported Surface](SUPPORTED_SURFACE.md) and [Features](FEATURES.md) for
executable commands. Prices and completion times below are historical examples,
not estimates or guarantees; run `deepr research ... --preview` for the current
maximum.

---

## Investment Due Diligence

```bash
deepr research "Commercial real estate market in Austin Texas: cap rates, vacancy trends, development pipeline, demographic shifts" --provider openai --model o4-mini-deep-research --budget 2
```

### Scenario

A real estate investor needs comprehensive market intelligence before a $20M acquisition. Deepr researches market fundamentals, supply dynamics, tenant demand drivers, and risk factors across multiple data sources.

### Outcome

- Current cap rates by property type and submarket
- 5-year vacancy trends and absorption rates
- Development pipeline analysis with delivery timelines
- Employment and population growth projections
- Cited recommendations on pricing and timing

### Real Benefit

The intended benefit is a repeatable, cited research artifact with an explicit
budget ceiling. Actual time and cost depend on the selected bounded route.

---

## Regulatory Compliance Research

```bash
deepr research "GDPR and CCPA requirements for SaaS platforms handling EU and California customer data" --provider openai --model o4-mini-deep-research --budget 2
```

### Scenario

A compliance officer needs current regulatory guidance before a product launch. Deepr synthesizes legal requirements, technical controls, documentation needs, and penalty risks from authoritative sources.

### Outcome

- Specific data handling requirements by jurisdiction
- Required technical safeguards and consent mechanisms
- Documentation and reporting obligations
- Penalty structures and enforcement precedents
- Implementation checklist with priority levels

### Real Benefit

A cited preliminary research artifact for expert review. This is not legal
advice, and provider completion time is not guaranteed.

---

## Strategic Business Decision

```bash
deepr research "Should our manufacturing company invest in solar panels and battery storage for our facility? Compare financial, operational, and sustainability perspectives." --provider openai --model o4-mini-deep-research --budget 2
```

### Scenario

Leadership needs multi-angle analysis on a $2M capital decision. Deepr examines financial returns, operational impacts, risks, incentives, and strategic positioning from diverse expert perspectives.

### Outcome

- Financial analysis: ROI, payback period, tax incentives, financing options
- Operational perspective: Energy independence, backup power, maintenance
- Risk assessment: Technology obsolescence, utility rate changes, policy shifts
- Environmental impact: Carbon reduction, ESG reporting, brand value
- Strategic synthesis: Weighted recommendation with decision criteria

### Real Benefit

Weeks of cross-functional research compressed into one comprehensive report, revealing considerations each department might miss.

---

## Technical Implementation Research

```bash
deepr research "PostgreSQL connection pooling and read replica strategies for high-traffic web applications" --provider openai --model o4-mini-deep-research --budget 2
```

### Scenario

A development team needs to scale their database infrastructure to handle 10x traffic growth.

### Outcome

- Connection pooling strategies (PgBouncer vs Pgpool-II)
- Read replica configuration and routing patterns
- Performance benchmarks and capacity planning
- Common pitfalls and troubleshooting guides
- Implementation checklist with code examples

### Cost

Run `--preview` first. The exact maximum and provider completion time replace a
fixed cost or duration claim.

---

## Competitive Intelligence

```bash
deepr research "Current public sentiment on autonomous vehicle safety" --provider openai --model o4-mini-deep-research --budget 2
```

### Scenario

An automotive company needs to understand public perception before a major product announcement.

### Outcome

- Real-time sentiment analysis from social platforms
- Key concerns and objections identified
- Demographic breakdown of opinions
- Trending topics and viral discussions
- PR strategy recommendations

### Cost

Run `--preview` first. xAI server-side search is gated because its invocation
cost has no complete request ceiling.

---

## Local Expert Learning: Kubernetes

Build and maintain a local expert without a metered campaign:

```bash
# 1. Seed from local documents
deepr expert make "Kubernetes Expert" --local --files "docs/kubernetes/*.md"

# 2. Add fresh free retrieval context through local capacity
deepr expert subscribe "Kubernetes Expert" "Kubernetes networking and managed service changes"
deepr expert sync "Kubernetes Expert" --local --fresh-context -y

# 3. Consult stored state locally
deepr expert consult "Should we self-host Kubernetes or use EKS/GKE?" --experts "Kubernetes Expert" --local
```

### Total Cost

Local model provider cost is `$0`; local electricity is outside Deepr's ledger.

---

## Strategic Research Scenario

```bash
deepr research "Evaluate an acquisition target across financial viability, market position, cultural fit, and integration risks" --provider openai --model o4-mini-deep-research --budget 2
```

### What Happens

**Phase 1 (Foundation):**
- Document target company financials
- Research market competitive landscape
- Document cultural indicators and employee sentiment

**Phase 2 (Analysis):**
- Analyze financial health and projections
- Evaluate competitive positioning and moat
- Assess cultural compatibility with acquiring company

**Phase 3 (Synthesis):**
- Integration risk assessment
- Synergy opportunities
- Go/no-go recommendation with reasoning

Metered multi-phase execution is gated. This direct example is one bounded job;
preview its exact maximum before running.

---

## Creating Domain Experts

```bash
# Create expert from your proprietary documents
deepr expert make "Azure Fabric Expert" \
  --local \
  --files "./docs/*.md" \
  --description "Azure Landing Zones and Fabric governance"

# Create another local expert
deepr expert make "Supply Chain Management" \
  --local \
  --files "C:\Docs\*.pdf"
```

### What Happens

1. Deepr creates a provider-free local profile.
2. Local files enter the verified expert learning path.
3. The structured belief store remains canonical.
4. Future maintenance can use local or explicit non-metered plan capacity.

---

## Local Expert Consultation

```bash
deepr expert consult "How should we handle OneLake security for multi-tenant SaaS?" --experts "Azure Fabric Expert" --local
```

### Example Conversation

```
You: How should we handle OneLake security for multi-tenant SaaS?

Expert: Based on stored evidence, three approaches need comparison:
1. Workspace-per-tenant isolation [Source: stored belief provenance]
2. Lakehouse-per-tenant with RLS [Source: stored belief provenance]
3. Shared lakehouse with strict RLS [Source: stored belief provenance]

For your SaaS scenario, I recommend approach 2...

Missing evidence remains a gap for a later explicit local, plan, or bounded
research action. The consult does not silently trigger paid research or write
new beliefs.
```

---

## Writing Better Prompts

### Vague Prompt (Poor)

```bash
deepr research "healthcare regulations" --provider openai --model o4-mini-deep-research --preview
```

This will produce generic, unfocused results.

### Specific Prompt (Good)

```bash
deepr research "Compare HIPAA, HITECH, and state privacy laws for telehealth services in California, Texas, and New York. Focus on consent requirements, data retention policies, breach notification timelines, and penalties. Include cross-state patient care implications. Provide compliance checklist for a telehealth platform serving all three states." --provider openai --model o4-mini-deep-research --preview
```

### Best Practices

1. **State the decision you need to make** - "Should we adopt X?" vs "Tell me about X"
2. **Specify the scope** - Technologies, timeframe, geographic constraints
3. **Mention what you'll do with the output** - "For compliance checklist", "To inform Q2 roadmap"
4. **Include constraints** - Cost limits, performance requirements, regulatory requirements
5. **Request specific formats** - Checklists, comparisons, timelines, decision matrices

### Template Pattern

```
deepr research "[ACTION] [TOPIC] for [CONTEXT]. Focus on [ASPECTS]. Include [DELIVERABLE]."
```

Example:
```
deepr research "Evaluate API gateway options (Kong, Tyk, AWS API Gateway) for fintech platform handling 100K requests/minute. Focus on latency, cost, compliance (PCI-DSS), and operational complexity. Include TCO comparison and implementation checklist." --provider openai --model o4-mini-deep-research --preview
```

---

## Advanced Context Integration

Hosted document attachment is gated in v2.36. Build a local expert from the
documents and consult it locally, or submit a separate bounded provider research
job without hosted file context.

```bash
deepr expert make "Roadmap Expert" --local --files "C:\Documents\q4-roadmap.pdf"
deepr expert consult "Compare the roadmap with stored evidence" --experts "Roadmap Expert" --local
```

---

## Prompt Refinement

The `PromptRefiner` substrate is not wired into the supported research command,
so `DEEPR_AUTO_REFINE` must not be treated as an active feature. Write the
desired scope directly. A vague prompt such as "llm pricing" could instead be
expanded by the operator to include:
- Pricing models across providers (per-token, per-request, subscription)
- Cost per token by model tier
- Volume discounts and enterprise pricing
- Total cost of ownership comparisons
- Cost optimization strategies

---

## Vector Knowledge Stores

New provider vector-store creation and research attachment are gated in v2.36
until upload, indexing, retention, retrieval, and cleanup costs share the same
reservation. For a local corpus, use `deepr expert make NAME --local --files`.

---

See also:
- [MODELS.md](MODELS.md) - Provider comparison, costs, model selection
- [EXPERTS.md](EXPERTS.md) - Creating and using domain experts
