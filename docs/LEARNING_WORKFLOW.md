# Structured Learning Workflow with Deepr

**Philosophy**: Learning is not a single activity - it's a mix of staying current (news), understanding fundamentals (docs), deep thinking (research), and strategic discussion (team).

## The Four Types of Knowledge Artifacts

### 1. News (`news-{topic}.md`)
**Purpose**: Track latest developments, announcements, releases
**Cadence**: Daily/Weekly
**Model**: Fast (grok-4-fast, gemini-2.5-flash)
**Cost**: $0.0005-$0.001 per update

**What goes here**:
- Latest releases and version updates
- Recent announcements from vendors
- Security vulnerabilities discovered
- Breaking changes and deprecations
- Conference talks and blog posts
- Community discussions (HN, Reddit, Twitter)

**Example files**:
- `news-kubernetes.md` - Weekly K8s releases and announcements
- `news-ai-coding-tools.md` - Latest AI assistant releases
- `news-aws-services.md` - New AWS features and services
- `news-security-vulnerabilities.md` - CVEs and security patches

**Command**:
```bash
# Initial creation
deepr news "Kubernetes latest developments" > news-kubernetes.md

# Weekly updates (append)
deepr news "Kubernetes updates" --since "last week" >> news-kubernetes.md

# With source filtering
deepr news "AWS announcements" --sources "aws,hn,reddit" > news-aws-services.md
```

**When to use**:
- Starting your day/week (catch up on what's new)
- Before making technology decisions (is it actively maintained?)
- Preparing for conversations (know what people are talking about)
- Competitive intelligence (track rival products)

---

### 2. Docs (`docs-{topic}.md`)
**Purpose**: Understand fundamentals, APIs, official documentation
**Source**: Official documentation, API references, specs
**Model**: Fast with scraping (grok-4-fast)
**Cost**: $0.001-$0.003 per scrape+summarize

**What goes here**:
- Official API documentation
- Framework guides and best practices
- Cloud provider architecture docs (CAF, Well-Architected)
- Compliance frameworks (SOC2, HIPAA, GDPR)
- Product specifications and feature matrices
- SDK usage examples

**Example files**:
- `docs-aws-caf.md` - AWS Cloud Adoption Framework
- `docs-react-server-components.md` - React RSC official guide
- `docs-kubernetes-networking.md` - K8s networking concepts
- `docs-oauth2-spec.md` - OAuth 2.0 specification

**Command**:
```bash
# Scrape and summarize official docs
deepr research "Summarize the AWS Cloud Adoption Framework" \
  --scrape https://docs.aws.amazon.com/caf \
  --model grok-4-fast \
  > docs-aws-caf.md

# From PDF
deepr research "Extract key concepts from OAuth 2.0 spec" \
  --upload oauth2-rfc6749.pdf \
  --model grok-4-fast \
  > docs-oauth2-spec.md

# API documentation
deepr research "Document Stripe API payment flows" \
  --scrape https://docs.stripe.com/api \
  --model grok-4-fast \
  > docs-stripe-api.md
```

**When to use**:
- Starting to learn a new technology
- Reference during implementation
- Onboarding new team members
- Compliance/audit preparation

---

### 3. Research (`research-{topic}.md`)
**Purpose**: Deep analysis, synthesis, novel problem-solving
**Depth**: High - extended reasoning and multi-source synthesis
**Model**: Deep research (o4-mini, o3) OR fast for breadth
**Cost**: $0.001-$5.00 depending on depth needed

**What goes here**:
- Technology comparisons and evaluations
- Architecture design decisions
- Performance optimization strategies
- Security analysis and threat modeling
- Algorithm selection and trade-offs
- Multi-source research synthesis

**Example files**:
- `research-api-gateway-comparison.md` - Kong vs Envoy vs Nginx
- `research-database-scaling-strategies.md` - Sharding, replication, CQRS
- `research-zero-trust-architecture.md` - Implementing zero-trust
- `research-cost-optimization-aws.md` - AWS cost reduction strategies

**Command**:
```bash
# Deep research (novel problem-solving)
deepr research "Compare API gateway solutions for high-throughput microservices" \
  --model o4-mini-deep-research \
  > research-api-gateway-comparison.md

# Fast research (breadth over depth)
deepr research "What are the latest container security best practices?" \
  --model grok-4-fast \
  > research-container-security.md

# With context
deepr research "How should we scale our PostgreSQL database to 10M users?" \
  --upload current-architecture.pdf \
  --model o3-deep-research \
  > research-database-scaling-strategies.md
```

**When to use**:
- Making critical technology decisions
- Solving complex technical problems
- Understanding trade-offs between approaches
- Preparing architecture proposals

---

### 4. Team (`team-{topic}.md`)
**Purpose**: Strategic discussion, multiple perspectives, decision-making
**Format**: Multi-perspective analysis with conflict exploration
**Model**: Fast for cost-effective diverse viewpoints (grok-4-fast)
**Cost**: $0.003-$0.006 for 6 perspectives

**What goes here**:
- Strategic decisions (build vs buy, architecture pivots)
- Product direction debates
- Risk assessment from multiple angles
- Stakeholder perspective analysis
- Mock board-level discussions
- Devil's advocate scenarios

**Example files**:
- `team-microservices-migration.md` - Should we migrate?
- `team-open-source-strategy.md` - Open source our platform?
- `team-market-entry-japan.md` - International expansion decision
- `team-ai-code-review-adoption.md` - Adopt AI code review?

**Command**:
```bash
# 6 perspectives on strategic question
deepr team "Should we migrate our monolith to microservices?" \
  --perspectives 6 \
  --model grok-4-fast \
  > team-microservices-migration.md

# With context
deepr team "Should we open source our core platform?" \
  --perspectives 8 \
  --context "$(cat company-context.txt)" \
  --model grok-4-fast \
  > team-open-source-strategy.md

# Adversarial mode (devil's advocate weighted)
deepr team "Should we acquire CompanyX for $50M?" \
  --perspectives 6 \
  --adversarial \
  --model grok-4-fast \
  > team-acquisition-decision.md
```

**When to use**:
- Before making major strategic decisions
- When you need to challenge your assumptions
- Preparing for board presentations
- Risk assessment before launches
- Understanding stakeholder concerns

---

## Learning Workflow Example

### Scenario: Learning Kubernetes for Production

#### Week 1: Foundations
```bash
# 1. Get the official docs
deepr research "Summarize Kubernetes core concepts" \
  --scrape https://kubernetes.io/docs/concepts \
  --model grok-4-fast \
  > docs-kubernetes-core.md

# 2. What's happening in the ecosystem?
deepr news "Kubernetes latest developments" \
  > news-kubernetes.md

# 3. Deep dive into networking (complex topic)
deepr research "Kubernetes networking deep dive - CNI, Services, Ingress" \
  --model o4-mini-deep-research \
  > research-kubernetes-networking.md
```

#### Week 2: Production Considerations
```bash
# 4. Security best practices (scrape official docs)
deepr research "Kubernetes security best practices" \
  --scrape https://kubernetes.io/docs/concepts/security \
  --model grok-4-fast \
  > docs-kubernetes-security.md

# 5. Real-world production challenges (research)
deepr research "Kubernetes production challenges and solutions" \
  --model grok-4-fast \
  > research-kubernetes-production.md

# 6. Strategic decision (team discussion)
deepr team "Should we self-host Kubernetes or use EKS/GKE?" \
  --perspectives 6 \
  --model grok-4-fast \
  > team-kubernetes-hosting-decision.md
```

#### Ongoing: Stay Current
```bash
# Weekly news updates
deepr news "Kubernetes updates" --since "last week" \
  >> news-kubernetes.md

# Security monitoring
deepr news "Kubernetes security vulnerabilities" --since "last month" \
  >> news-kubernetes-security.md
```

---

## File Organization Structure

```
knowledge/
├── news/
│   ├── news-kubernetes.md
│   ├── news-aws-services.md
│   ├── news-ai-coding-tools.md
│   └── news-security-vulnerabilities.md
│
├── docs/
│   ├── docs-aws-caf.md
│   ├── docs-kubernetes-networking.md
│   ├── docs-react-server-components.md
│   └── docs-oauth2-spec.md
│
├── research/
│   ├── research-api-gateway-comparison.md
│   ├── research-database-scaling-strategies.md
│   ├── research-zero-trust-architecture.md
│   └── research-cost-optimization-aws.md
│
└── team/
    ├── team-microservices-migration.md
    ├── team-open-source-strategy.md
    ├── team-ai-code-review-adoption.md
    └── team-market-entry-japan.md
```

---

## Model Selection by Type

| Type | Model | Cost | Rationale |
|------|-------|------|-----------|
| **news** | grok-4-fast | $0.0008 | Recency matters, not depth. Web search + fast response |
| **docs** | grok-4-fast | $0.002 | Summarizing existing content. Large context window (2M tokens) |
| **research** (breadth) | grok-4-fast | $0.001 | Quick exploration, multiple sources |
| **research** (depth) | o4-mini-deep-research | $0.50 | Novel problem-solving, extended reasoning needed |
| **team** | grok-4-fast | $0.005 | Cost-effective for 6+ perspectives |

---

## Automated Workflows

### Daily Standup Prep
```bash
#!/bin/bash
# daily-update.sh

# Update news for domains I track
deepr news "AI developments" --since yesterday >> knowledge/news/news-ai.md
deepr news "AWS announcements" --since yesterday >> knowledge/news/news-aws.md
deepr news "Kubernetes updates" --since yesterday >> knowledge/news/news-kubernetes.md

# Check for critical security issues
deepr news "security vulnerabilities" --severity critical --since "3 days" \
  >> knowledge/news/news-security.md

echo "Daily update complete. Check knowledge/news/ for latest."
```

### Weekly Learning Session
```bash
#!/bin/bash
# weekly-deep-dive.sh

TOPIC=$1

# 1. Get official docs
deepr research "Summarize $TOPIC fundamentals and best practices" \
  --model grok-4-fast \
  > "knowledge/docs/docs-${TOPIC}.md"

# 2. Track news
deepr news "$TOPIC latest developments" \
  > "knowledge/news/news-${TOPIC}.md"

# 3. Deep research
deepr research "Advanced $TOPIC patterns and architectures" \
  --model o4-mini-deep-research \
  > "knowledge/research/research-${TOPIC}-advanced.md"

echo "Created 3 knowledge artifacts for: $TOPIC"
```

### Strategic Decision Framework
```bash
#!/bin/bash
# strategic-decision.sh

QUESTION=$1

# 1. Research the options
deepr research "$QUESTION - comprehensive analysis" \
  --model o4-mini-deep-research \
  > "knowledge/research/research-${QUESTION//[: ]/-}.md"

# 2. Get team perspectives
deepr team "$QUESTION" \
  --perspectives 8 \
  --adversarial \
  --model grok-4-fast \
  > "knowledge/team/team-${QUESTION//[: ]/-}.md"

# 3. Latest news context
deepr news "$QUESTION" --since "last month" \
  > "knowledge/news/news-${QUESTION//[: ]/-}.md"

echo "Strategic decision package created for: $QUESTION"
```

---

## Expert System Integration

Once you've built up knowledge artifacts, feed them to experts:

```bash
# Create a Kubernetes expert
deepr expert make "Kubernetes Expert" \
  -f knowledge/docs/docs-kubernetes-*.md \
  -f knowledge/research/research-kubernetes-*.md \
  -f knowledge/news/news-kubernetes.md \
  -d "Expert on Kubernetes with latest docs, research, and news"

# Chat with expert (it has all your curated knowledge)
deepr expert chat "Kubernetes Expert"
```

The expert now knows:
- ✅ Fundamentals (docs)
- ✅ Latest developments (news)
- ✅ Deep analysis (research)
- ✅ Strategic considerations (team discussions)

---

## Summary: The Learning Cycle

```
1. NEWS (Daily)
   ↓ What's changing?

2. DOCS (As needed)
   ↓ What are the fundamentals?

3. RESEARCH (Deep dive)
   ↓ How does it work? What are trade-offs?

4. TEAM (Strategic)
   ↓ Should we adopt it? What are risks?

5. EXPERT (Synthesis)
   ↓ Feed all artifacts to expert for Q&A

6. Back to NEWS (Stay current)
```

This mirrors how actual experts build and maintain knowledge:
- **Currency** through news monitoring
- **Depth** through official docs and research
- **Wisdom** through strategic team discussions
- **Accessibility** through expert systems

Deepr makes this workflow **fast** (seconds, not hours) and **affordable** (pennies, not dollars).
