# Model Selection Strategy for Deepr

**Last Updated**: 2025-11-12
**Status**: Recommended Best Practices

## Overview

Deepr supports multiple AI providers and models, each optimized for different use cases. This document provides guidance on when to use deep research models vs fast/general models, and introduces the concept of specialized commands for different research needs.

## Model Categories

### Deep Research Models (Extended Reasoning)
**Providers**: OpenAI, Azure OpenAI
**Models**: `o4-mini-deep-research`, `o3-deep-research`

**Characteristics**:
- Extended reasoning chains (thinking tokens)
- Async execution (5-15 minutes per query)
- High cost ($0.50-$5.00 per query)
- Deep synthesis and novel problem-solving
- Unique Deep Research API (not available from other providers)

### Fast Models (Immediate Completion)
**Providers**: xAI (Grok), Google (Gemini), Anthropic (Claude)
**Models**: `grok-4-fast`, `gemini-2.5-flash`, `claude-sonnet-4-5`

**Characteristics**:
- Immediate/streaming responses (10-60 seconds)
- Low cost ($0.0005-$0.003 per query)
- Large context windows (2M tokens for Grok)
- Excellent for breadth, recency, and speed
- 96-99% cheaper than deep research models

## When to Use Deep Research Models

Use `o4-mini-deep-research` or `o3-deep-research` for:

### 1. Novel Problem-Solving
- **Unique challenges** requiring extended reasoning
- **Complex technical architectures** needing careful analysis
- **Multi-constraint optimization** (performance, cost, security, maintainability)

**Example**:
```bash
deepr research "Design a distributed rate limiting system for 1M RPS with 99.99% accuracy and <1ms overhead" \
  --model o4-mini-deep-research
```

### 2. Critical Strategic Decisions
- **M&A analysis** - Due diligence and valuation
- **Technology pivots** - Architecture rewrites or platform changes
- **Market entry** - International expansion, new verticals

**Example**:
```bash
deepr research "Should we migrate our monolith to microservices? Consider our 50-person team, 10-year codebase, and 99.9% uptime SLA" \
  --model o3-deep-research --upload current_architecture.pdf
```

### 3. Deep Synthesis
- **Research paper analysis** - Connecting findings across multiple papers
- **Patent landscape** - Prior art search and novelty assessment
- **Comprehensive documentation** - System design docs requiring deep technical accuracy

**Example**:
```bash
deepr research "Synthesize the last 5 years of research on transformer efficiency improvements" \
  --model o3-deep-research
```

### 4. Complex Multi-Step Reasoning
- **Security audits** - Finding subtle vulnerabilities
- **Performance debugging** - Root cause analysis across distributed systems
- **Algorithm design** - Novel solutions to computational problems

## When to Use Fast Models

Use `grok-4-fast`, `gemini-2.5-flash`, or similar for:

### 1. Latest News & Best Practices
**Perfect for**: Staying current with rapidly evolving fields

**Why Fast Models Excel**:
- **Recency bias**: Web search pulls latest information
- **Breadth over depth**: Cover multiple sources quickly
- **Speed**: Get answers in 30 seconds, not 10 minutes
- **Cost**: Check daily without breaking the bank

**Example**:
```bash
# Traditional approach (slow, expensive)
deepr research "What's new in Kubernetes 1.32?" --model o4-mini-deep-research
# Cost: $0.50, Time: 10 minutes

# Optimized approach (fast, cheap)
deepr research "What's new in Kubernetes 1.32?" --model grok-4-fast
# Cost: $0.0008, Time: 30 seconds
```

**Use Cases**:
- "What are the latest AI coding tools released this month?"
- "Recent security vulnerabilities in Next.js"
- "Best practices for React Server Components in 2025"
- "New features in Python 3.13"

### 2. Multiple Perspectives (Team Research)
**Perfect for**: Exploring diverse viewpoints on complex questions

**Why Fast Models Excel**:
- **Parallel execution**: 6 perspectives simultaneously
- **Cost efficiency**: $0.005 total vs $3.00 with deep research
- **Diverse insights**: Each perspective brings unique angle
- **Speed**: Complete in 2-3 minutes

**Example**:
```bash
# 6 perspectives analyzing a strategic question
deepr team "Should we build or buy our data pipeline?" --perspectives 6 --model grok-4-fast
# Cost: ~$0.005 for 6 perspectives
# Time: 2 minutes
# Output: 6 expert viewpoints (Infrastructure Lead, Data Engineer, CTO, etc.)
```

### 3. Learning Campaigns (Breadth-First Exploration)
**Perfect for**: Building knowledge in a new domain

**Why Fast Models Excel**:
- **Rapid iteration**: Cover multiple topics quickly
- **Affordable depth**: 10 topics for the cost of 1 deep research
- **Progressive learning**: Start broad, then go deep where needed

**Example**:
```bash
# Multi-phase learning campaign
deepr learn "Docker container security" --phases 5 --model grok-4-fast
# Cost: ~$0.004 (5 phases × $0.0008)
# Time: 3-5 minutes
# Phases: 1) Fundamentals, 2) Best practices, 3) Vulnerabilities, 4) Tools, 5) Case studies
```

### 4. Expert Chat & Q&A
**Perfect for**: Interactive knowledge exploration

**Why Fast Models Excel**:
- **Conversation flow**: Quick back-and-forth
- **Large context**: 2M tokens fits entire documentation
- **Cost-effective**: Hundreds of questions for $1

**Example**:
```bash
# Create expert with knowledge base
deepr expert make "Kubernetes Expert" \
  -f kubernetes-docs.pdf \
  -f production-runbook.md \
  -f incident-reports/

# Chat with expert (uses grok-4-fast by default)
deepr expert chat "Kubernetes Expert"
# Each message: ~$0.0005
```

### 5. Context Summarization
**Perfect for**: Distilling large documents

**Why Fast Models Excel**:
- **Huge context windows**: 2M tokens = 1.5M words
- **Speed**: Summarize in seconds
- **Cost**: Pennies per document

**Example**:
```bash
deepr research "Summarize this 500-page technical spec" \
  --upload technical-spec.pdf \
  --model grok-4-fast
# Cost: ~$0.002
```

### 6. Planning & Orchestration
**Perfect for**: Research planning before execution

**Strategy**: Use fast reasoning (GPT-5, Claude Sonnet) for planning, then execute with appropriate models

**Example**:
```bash
# GPT-5 plans the research campaign
deepr prep plan "Analyze AI code review market" --planner gpt-5 --topics 8
# Cost: ~$0.01 (planning only)

# Review and adjust plan
deepr prep review

# Execute with appropriate models
deepr prep execute --model grok-4-fast  # Or o4-mini if deep analysis needed
```

## Proposed: "deepr news" Command

### Concept
A specialized command optimized for tracking latest developments in technology, perfect for:
- Daily standup prep ("What happened in AI yesterday?")
- Weekly tech newsletters
- Competitive intelligence
- Security monitoring

### Design

#### Basic Usage
```bash
# Get latest news in a domain
deepr news "AI coding assistants"
deepr news "Kubernetes releases"
deepr news "React ecosystem"

# Time-bounded queries
deepr news "Python security vulnerabilities" --since "last week"
deepr news "OpenAI announcements" --since "last month"

# Source filtering
deepr news "JavaScript frameworks" --sources "github,hn,reddit"
deepr news "Cloud security" --sources "aws,azure,gcp,security-advisories"

# Format options
deepr news "Docker updates" --format brief     # Bullet points
deepr news "Kubernetes" --format detailed      # Full articles
deepr news "AI research" --format digest       # Weekly digest
```

#### Implementation Strategy

**Model Selection**: Always use fast models (grok-4-fast default)
- **Reasoning**: News is about recency and breadth, not deep reasoning
- **Cost**: Pennies per query enables daily monitoring
- **Speed**: 30-second responses keep you in flow

**Search Strategy**:
1. **Web search first**: Get latest indexed content
2. **Source diversity**: Mix official sources (blogs, changelogs) with community (HN, Reddit, Twitter)
3. **Date filtering**: Prioritize recent content
4. **Deduplication**: Cluster similar news items

**Output Format**:
```markdown
# Latest in [Topic] (2025-11-12)

## 🔥 Top Stories
- [Most significant development]
- [Second most significant]

## 📰 Recent Announcements
- Company X released Y (November 10, 2025)
- Framework Z version 2.0 beta (November 8, 2025)

## 🐛 Security & Bugs
- CVE-2025-XXXX: Critical vulnerability in [package]
- Bug fix in [tool] affecting [use case]

## 💡 Community Highlights
- Popular GitHub repo: [repo] (1.5k stars this week)
- HN discussion: [topic] (500+ comments)

## 📚 Resources
- [Tutorial/guide released this week]
- [Conference talk published]

---
Generated with deepr news using grok-4-fast
Cost: $0.0008 | Time: 23s | Sources: 45
```

### Use Cases

#### Daily Tech Monitoring
```bash
# Morning routine
deepr news "AI developments" --since yesterday --format brief
deepr news "security-vulnerabilities" --severity critical --since "3 days"
```

#### Competitive Intelligence
```bash
# Track competitors
deepr news "Anthropic OR OpenAI OR Google AI" --since "last week"
deepr news "React OR Vue OR Svelte releases" --format detailed
```

#### Project-Specific Tracking
```bash
# Monitor dependencies
deepr news "Next.js OR Vercel updates" --since "last month"
deepr news "PostgreSQL OR Supabase news" --format digest
```

## Cost Comparison: Real-World Scenarios

### Scenario 1: Weekly Tech Newsletter
**Goal**: Stay current with 5 tech domains

**Deep Research Approach**:
```bash
# 5 topics × $0.50 = $2.50 per week
# Annual cost: $130
```

**Fast Model Approach**:
```bash
# 5 topics × $0.0008 = $0.004 per week
# Annual cost: $0.21
```

**Savings**: 99.8% ($129.79/year)

### Scenario 2: Team Research Session
**Goal**: Analyze strategic question from 6 perspectives

**Deep Research Approach**:
```bash
# 6 perspectives × $0.50 = $3.00 per session
deepr team "Should we migrate to microservices?" --model o4-mini-deep-research
```

**Fast Model Approach**:
```bash
# 6 perspectives × $0.0008 = $0.0048 per session
deepr team "Should we migrate to microservices?" --model grok-4-fast
```

**Savings**: 99.8% ($2.995 per session)

### Scenario 3: Learning New Technology
**Goal**: Multi-phase learning campaign (5 phases)

**Deep Research Approach**:
```bash
# 5 phases × $0.50 = $2.50 per learning campaign
deepr learn "Kubernetes operators" --phases 5 --model o4-mini-deep-research
```

**Fast Model Approach**:
```bash
# 5 phases × $0.0008 = $0.004 per learning campaign
deepr learn "Kubernetes operators" --phases 5 --model grok-4-fast
```

**Savings**: 99.8% ($2.496 per campaign)

## Recommended Strategy: Hybrid Approach

### 80/20 Rule
- **80% of operations**: Use fast models (grok-4-fast, gemini-2.5-flash)
  - News monitoring
  - Team research
  - Learning campaigns
  - Expert chat
  - Planning
  - Context summarization

- **20% of operations**: Use deep research (o4-mini, o3)
  - Novel problem-solving
  - Critical decisions
  - Deep synthesis
  - Complex reasoning

### Expected Cost Savings
With 80/20 split:
- **Without optimization**: 100% deep research = $100/month
- **With optimization**: (80% × $0.0008) + (20% × $0.50) = $0.064 + $10 = **$10.06/month**
- **Total savings**: 90% ($89.94/month)

### Environment Configuration
```bash
# Default to fast models for general operations
export DEEPR_DEFAULT_PROVIDER=xai
export DEEPR_DEFAULT_MODEL=grok-4-fast

# Use OpenAI only for deep research
export DEEPR_DEEP_RESEARCH_PROVIDER=openai
export DEEPR_DEEP_RESEARCH_MODEL=o4-mini-deep-research
```

## Command Quick Reference

| Command | Default Model | Override Example | Best For |
|---------|--------------|------------------|----------|
| `deepr research` | Auto-detect | `--model grok-4-fast` | General research |
| `deepr team` | Auto-detect | `--model grok-4-fast` | Multiple perspectives |
| `deepr learn` | Auto-detect | `--model grok-4-fast` | Learning campaigns |
| `deepr expert chat` | grok-4-fast | N/A | Q&A with experts |
| `deepr prep plan` | gpt-5 (planning) | `--model grok-4-fast` (execution) | Research campaigns |
| `deepr news` (proposed) | grok-4-fast | N/A | Latest developments |

## Summary

**Think of it like this**:
- **Deep Research Models** = "Hire a PhD researcher for 10 hours" ($0.50-$5.00)
- **Fast Models** = "Ask an expert for 30 seconds" ($0.0005-$0.003)

**When building expertise**:
- Part of being an expert is knowing the **latest news** → Fast models
- Part of being an expert is **deep understanding** → Mix of both
- Part of being an expert is **novel problem-solving** → Deep research models

**The "deepr news" concept** recognizes that staying current doesn't require deep reasoning - it requires:
- **Recency**: Latest information from web search
- **Breadth**: Multiple sources and perspectives
- **Speed**: Quick turnaround to stay in flow
- **Affordability**: Daily monitoring without breaking the bank

This is exactly what fast models were designed for.
