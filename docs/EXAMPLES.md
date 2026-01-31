# Deepr Examples

Detailed real-world examples demonstrating Deepr's capabilities across different domains.

---

## Investment Due Diligence

```bash
deepr learn "Commercial real estate market in Austin Texas: cap rates, vacancy trends, development pipeline, demographic shifts"
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

Professional-grade market analysis in 45 minutes for $3, versus $5K consultant fees and 2-week turnaround.

---

## Regulatory Compliance Research

```bash
deepr research "GDPR and CCPA requirements for SaaS platforms handling EU and California customer data"
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

Clear compliance roadmap in 20 minutes, avoiding costly legal consultations for preliminary research.

---

## Strategic Business Decision

```bash
deepr team "Should our manufacturing company invest in solar panels and battery storage for our facility?"
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
deepr research "PostgreSQL connection pooling and read replica strategies for high-traffic web applications" --scrape https://www.postgresql.org/docs/
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

$0.50-$2.00 depending on depth, 15-30 minutes

---

## Competitive Intelligence

```bash
deepr research "Current social media sentiment on autonomous vehicle safety" --provider grok
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

$0.50-$1.50 using Grok with X search integration

---

## Learning Campaign: Kubernetes

Complete learning workflow from fundamentals to strategic decision:

```bash
# 1. NEWS: What's happening in the ecosystem?
deepr news "Kubernetes latest developments" > knowledge/news/news-kubernetes.md

# 2. DOCS: What are the fundamentals?
deepr research "Summarize Kubernetes core concepts" \
  --scrape https://kubernetes.io/docs/concepts \
  --model grok-4-fast \
  > knowledge/docs/docs-kubernetes-core.md

# 3. RESEARCH: How does it work? What are trade-offs?
deepr research "Kubernetes networking deep dive - CNI, Services, Ingress" \
  --model o4-mini-deep-research \
  > knowledge/research/research-kubernetes-networking.md

# 4. TEAM: Should we adopt it? What are risks?
deepr team "Should we self-host Kubernetes or use EKS/GKE?" \
  --perspectives 6 \
  --model grok-4-fast \
  > knowledge/team/team-kubernetes-hosting-decision.md
```

### Total Cost

Approximately $0.51:
- News: $0.0008
- Docs: $0.002
- Research (deep): $0.50
- Team (6 perspectives): $0.005

---

## Multi-Phase Strategic Research

```bash
deepr learn "Evaluate acquisition target: financial viability, market position, cultural fit, integration risks" --phases 3
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

### Cost

$5-$15 depending on depth and context size

---

## Creating Domain Experts

```bash
# Create expert from your proprietary documents
deepr expert make "Azure Fabric Expert" \
  --files "./docs/*.md" \
  --description "Azure Landing Zones and Fabric governance"

# Have expert autonomously learn the domain
deepr expert make "Supply Chain Management" \
  --files "C:\Docs\*.pdf" \
  --learn \
  --budget 10
```

### What Happens (with --learn)

1. Expert analyzes initial documents
2. GPT-5.2 generates learning curriculum (5-20 research topics)
3. Shows estimated costs before submission
4. Submits deep research jobs to build comprehensive knowledge
5. Polls for completion and integrates results
6. You now have a domain expert ready for Q&A

### Cost

$5-$20 depending on domain complexity and number of research topics

---

## Expert Chat with Autonomous Learning

```bash
# Basic chat (uses knowledge base only)
deepr expert chat "Azure Fabric Expert"

# Agentic mode (can trigger research autonomously)
deepr expert chat "AWS Expert" --agentic --budget 5
```

### Example Conversation

```
You: How should we handle OneLake security for multi-tenant SaaS?

Expert: I have general OneLake concepts, but not specific multi-tenant SaaS patterns.
Let me research this to give you accurate guidance...

[Triggers: deepr research "OneLake multi-tenant security SaaS 2025" --mode docs]
[Cost: $0.15, Time: ~8 minutes]

Expert: My research found three approaches:
1. Workspace-per-tenant isolation [Source: Research job-abc123]
2. Lakehouse-per-tenant with RLS [Source: Research job-abc123]
3. Shared lakehouse with strict RLS [Source: Research job-abc123]

For your SaaS scenario, I recommend approach 2...

Should I remember this for future questions?

You: Yes

Expert: Added to my permanent knowledge base.

Session budget remaining: $4.83
```

---

## Writing Better Prompts

### Vague Prompt (Poor)

```bash
deepr research "healthcare regulations"
```

This will produce generic, unfocused results.

### Specific Prompt (Good)

```bash
deepr research "Compare HIPAA, HITECH, and state privacy laws for telehealth services in California, Texas, and New York. Focus on consent requirements, data retention policies, breach notification timelines, and penalties. Include cross-state patient care implications. Provide compliance checklist for a telehealth platform serving all three states."
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
deepr research "Evaluate API gateway options (Kong, Tyk, AWS API Gateway) for fintech platform handling 100K requests/minute. Focus on latency, cost, compliance (PCI-DSS), and operational complexity. Include TCO comparison and implementation checklist."
```

---

## Advanced Context Integration

```bash
# Combine proprietary documents with external research
deepr research "Review our Q4 product roadmap against competitor capabilities and market trends" \
  --upload "C:\Documents\q4-roadmap.pdf" \
  --upload "C:\Documents\competitor-analysis.xlsx"
```

Deepr will:
1. Parse and understand your internal documents
2. Research current market trends and competitor public information
3. Synthesize analysis combining internal and external data
4. Provide strategic recommendations grounded in both contexts

---

## Prompt Refinement

```bash
# Enable automatic prompt refinement
echo "DEEPR_AUTO_REFINE=true" >> .env

deepr research "llm pricing"
```

Vague prompt "llm pricing" automatically expands into:
- Pricing models across providers (per-token, per-request, subscription)
- Cost per token by model tier
- Volume discounts and enterprise pricing
- Total cost of ownership comparisons
- Cost optimization strategies

---

## Vector Knowledge Stores

```bash
# Build searchable knowledge base from research
deepr vector create --name "customer-feedback-2024" \
  --files "C:\Projects\interviews\*.pdf" "C:\Projects\reports\*.md"

# Query the knowledge base
deepr research "What are the top 3 feature requests across all customer interviews?" \
  --vector-store customer-feedback-2024
```

Create persistent knowledge bases from documents and past research. Query them semantically without re-uploading files.

---

See also:
- [LEARNING_WORKFLOW.md](LEARNING_WORKFLOW.md) - Structured learning strategies
- [MODEL_SELECTION.md](MODEL_SELECTION.md) - Choosing the right model for your task
- [EXPERT_SYSTEM.md](EXPERT_SYSTEM.md) - Creating and using domain experts
