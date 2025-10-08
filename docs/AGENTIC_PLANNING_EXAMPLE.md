# Agentic Planning: A Concrete Example

This document shows exactly how agentic planning works with a real example.

## User Goal

```
"I want to build an AI-powered code review tool"
```

## Traditional Approach (Not Agentic)

User runs 5 separate research queries:

1. "What AI code review tools exist?"
2. "What AI models can analyze code?"
3. "How do code review tools integrate with GitHub?"
4. "What do developers pay for code review tools?"
5. "How do I market a developer tool?"

**Problems:**
- Each query is isolated
- No context flows between reports
- User must manually connect findings
- Insights that span multiple reports are missed
- User does the synthesis work

**Result:** 5 isolated reports. User spends hours synthesizing.

## Agentic Approach (Deepr)

```bash
deepr prep plan "Build an AI code review tool" --topics 7
```

### Step 1: Planner Reasons About Information Architecture

**Planner's internal logic:**

"To build this successfully, the user needs to understand:

**Foundation Questions:**
- What exists? (market landscape)
- How does it work? (technical approaches)
- How do users access it? (integration patterns)

These can run in parallel—no dependencies.

**Analysis Questions:**
- Where are the opportunities? (requires: market + tech knowledge)
- How should we build it? (requires: tech + integration knowledge)

These MUST come after foundation—they need context.

**Strategic Questions:**
- How do we go to market? (requires: opportunities + architecture)
- What's the complete plan? (requires: everything)

These synthesize all prior research."

### Step 2: Generate Phased Plan

```
Phase 1: Foundation Research (Parallel - No Dependencies)
──────────────────────────────────────────────────────

Task 1: Market Landscape Analysis
Prompt: "Catalog existing AI-powered code review tools. For each,
        document: features, AI approach used, pricing model, target
        users, market positioning, and strengths/weaknesses. Include
        both established players (GitHub Copilot, Amazon CodeGuru)
        and emerging startups."

Est: $0.50, Time: 5-10 min

Task 2: AI Technical Approaches Survey
Prompt: "Survey approaches for AI-powered code analysis. Compare:
        - Static analysis with ML (traditional approach)
        - LLM-based analysis (GPT-4, Claude, etc.)
        - Specialized code models (CodeBERT, GraphCodeBERT)
        - Hybrid approaches
        For each: capabilities, accuracy, latency, cost, training needs."

Est: $0.50, Time: 5-10 min

Task 3: Integration Patterns Research
Prompt: "Research how code review tools integrate with development
        workflows. Cover: GitHub PR comments, GitLab MR reviews,
        IDE plugins (VSCode, IntelliJ), CLI tools, pre-commit hooks,
        CI/CD integration. Document: implementation patterns, user
        experience implications, adoption barriers."

Est: $0.50, Time: 5-10 min

Phase 2: Analysis Research (Sequential - Uses Phase 1 Context)
────────────────────────────────────────────────────────────

Task 4: Competitive Positioning Analysis [depends: 1, 2]
Prompt: "Context from previous research:
        [Summary of Task 1: Market landscape findings]
        [Summary of Task 2: Technical approaches analysis]

        Given this market and technical landscape, identify:
        - Gaps in current offerings (missing features, underserved users)
        - Technical opportunities (approaches not yet applied)
        - Positioning angles (how to differentiate)
        - Competitive vulnerabilities (where incumbents are weak)

        Provide specific recommendations for positioning a new tool."

Est: $0.50, Time: 5-10 min

Task 5: Architecture Recommendations [depends: 2, 3]
Prompt: "Context from previous research:
        [Summary of Task 2: Technical approaches comparison]
        [Summary of Task 3: Integration patterns]

        Based on technical capabilities and integration requirements,
        recommend specific architecture for an AI code review tool:
        - Which AI approach to use and why
        - How to structure the analysis pipeline
        - Which integrations to prioritize
        - How to handle different programming languages
        - Performance and cost trade-offs

        Provide concrete technical decisions."

Est: $0.50, Time: 5-10 min

Phase 3: Synthesis Research (Integrates All Context)
──────────────────────────────────────────────────

Task 6: Go-to-Market Strategy [depends: 1, 4, 5]
Prompt: "Context from all previous research:
        [Summary of Task 1: Market landscape]
        [Summary of Task 4: Competitive positioning opportunities]
        [Summary of Task 5: Recommended architecture]

        Develop comprehensive go-to-market strategy:
        - Target user segments (prioritized)
        - Pricing strategy (freemium, enterprise, per-seat)
        - Differentiation messaging
        - Launch sequence (beta, public, enterprise)
        - Partnership opportunities
        - Growth channels

        Reference specific market findings and competitive gaps."

Est: $0.50, Time: 5-10 min

Task 7: Executive Summary Report [depends: all]
Prompt: "Context from complete research campaign:
        [Summary of Task 1: Market landscape]
        [Summary of Task 2: Technical approaches]
        [Summary of Task 3: Integration patterns]
        [Summary of Task 4: Competitive positioning]
        [Summary of Task 5: Architecture recommendations]
        [Summary of Task 6: Go-to-market strategy]

        Synthesize into executive summary addressing:
        - Market opportunity (size, growth, trends)
        - Technical feasibility (approach, timeline, risks)
        - Competitive strategy (positioning, differentiation)
        - Go-to-market plan (users, pricing, launch)
        - Key risks and mitigations
        - Recommended next steps

        This should be the definitive document for decision-making."

Est: $0.80, Time: 10-15 min

Total: 7 tasks, ~$3.80, ~60 minutes
```

### Step 3: User Reviews Plan

```bash
deepr prep review

Shows the plan above, user can:
[ ] Remove tasks they don't need
[ ] Adjust priorities
[ ] Add custom context
```

### Step 4: Execute

```bash
deepr prep execute

Phase 1 execution:
  ✓ Task 1 complete (6 min, $0.52)
  ✓ Task 2 complete (7 min, $0.48)
  ✓ Task 3 complete (5 min, $0.44)

Phase 2 execution:
  → Task 4 starting...
     Injecting context from Tasks 1,2...
  ✓ Task 4 complete (8 min, $0.56)

  → Task 5 starting...
     Injecting context from Tasks 2,3...
  ✓ Task 5 complete (7 min, $0.51)

Phase 3 execution:
  → Task 6 starting...
     Injecting context from Tasks 1,4,5...
  ✓ Task 6 complete (9 min, $0.58)

  → Task 7 starting...
     Injecting context from all tasks...
  ✓ Task 7 complete (12 min, $0.83)

Campaign complete: 7 reports, $4.02, 54 minutes
```

## The Key Difference

### Without Context Chaining

Task 4 prompt: "Analyze competitive positioning in AI code review"

**Result:** Generic analysis based only on web search.

### With Context Chaining

Task 4 prompt: "Given [specific market findings from Task 1] and [technical capabilities from Task 2], identify gaps where current tools are weak..."

**Result:** Analysis that directly references prior findings, identifies specific opportunities that emerge from combining market + technical knowledge.

### Without Synthesis

User gets 7 separate reports and must:
- Read all 7 reports (30+ pages)
- Identify connections between findings
- Synthesize implications
- Make strategic decisions

**Time:** 2-3 hours of manual work

### With Synthesis

Task 7 integrates all findings into one executive summary that:
- Connects market opportunities to technical approaches
- Links competitive positioning to architecture choices
- Ties go-to-market strategy to differentiation points
- Provides clear, actionable recommendations

**Time:** Read one 5-page summary (10 minutes)

## Why This Is Profound

**Traditional:** AI executes research tasks
**Agentic:** AI reasons about research strategy

The planner doesn't just split a topic into subtopics. It:
1. **Understands** what information is needed
2. **Sequences** research to build context
3. **Connects** findings across phases
4. **Synthesizes** insights that span multiple reports

This is the difference between **automation** and **intelligence**.

## Real-World Impact

**Scenario:** CEO needs to decide whether to build AI code review tool

**Without Deepr:**
- CEO assigns to analyst
- Analyst spends 2 days researching
- Analyst spends 1 day synthesizing
- CEO gets report in 3 days
- Cost: $2,400 (analyst time)

**With Deepr:**
- CEO runs: `deepr prep plan "Build AI code review tool" --topics 7`
- Reviews plan (5 minutes)
- Runs: `deepr prep execute`
- Gets comprehensive analysis in 1 hour
- Cost: $4

**Result:** Same quality, 72x faster, 600x cheaper.

## The Vision

Deepr isn't just faster/cheaper. It's **fundamentally different**.

It automates not just the research, but the **strategy**:
- What questions to ask
- In what order
- How to connect findings
- What insights emerge from integration

This is what "agentic" means. Not just executing tasks, but reasoning about how to approach the problem.

**That's the innovation.**
