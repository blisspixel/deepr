# Cost Guidance Reference

This document provides detailed cost information and budget management guidance for Deepr operations.

## Cost Tables by Operation

### Research Operations

| Operation | Model | Typical Cost | Range |
|-----------|-------|--------------|-------|
| Web Search | N/A | FREE | $0 |
| Standard Research | grok-4-fast | $0.005 | $0.001-0.01 |
| Deep Research Mini | o4-mini-deep-research | $2.00 | $1.50-2.50 |
| Deep Research Full | o3-deep-research | $0.50 | $0.30-0.70 |
| Agentic Research | Multi-model | $3.00 | $1-10 |

### Expert Operations

| Operation | Typical Cost | Range |
|-----------|--------------|-------|
| Expert Query (no agentic) | $0.01 | $0.005-0.02 |
| Expert Query (agentic) | $2.00 | $0.50-5.00 |
| Expert Creation (docs only) | $0.10 | $0.05-0.20 |
| Expert Creation (with learning) | $5.00 | $2-10 |
| Fill Knowledge Gaps | $3.00 | $1-5 |

### Document Operations

| Operation | Typical Cost | Range |
|-----------|--------------|-------|
| Document Analysis | $0.02 | $0.01-0.05 |
| Multi-doc Synthesis | $0.10 | $0.05-0.20 |
| Large Document (>100 pages) | $0.50 | $0.20-1.00 |

## Budget Recommendations by Use Case

### Casual Research
- Budget: $1-2 per session
- Use: Standard research, expert queries
- Avoid: Deep research, agentic mode

### Professional Research
- Budget: $5-10 per session
- Use: Mix of standard and deep research
- Enable: Agentic expert queries with limits

### Comprehensive Analysis
- Budget: $10-25 per session
- Use: Deep research, agentic workflows
- Enable: Full autonomous capabilities

### Expert Building
- Budget: $10-20 per expert
- Use: Document ingestion + learning phases
- Plan: Multiple sessions for refinement

## Confirmation Thresholds

| Cost Level | Action Required |
|------------|-----------------|
| < $1 | No confirmation needed |
| $1-5 | Inform user of cost |
| $5-10 | Explicit confirmation required |
| > $10 | Strong confirmation + alternatives |

## Elicitation Decisions

When costs exceed budget, the system pauses and offers choices:

### APPROVE_OVERRIDE
- Proceed with the higher cost
- Use when: Task is critical, budget is flexible
- Risk: May significantly exceed original budget

### OPTIMIZE_FOR_COST
- Switch to cheaper models
- Use when: Results acceptable with less depth
- Trade-off: Reduced quality for lower cost

Model switching:
- o3-deep-research -> o4-mini-deep-research
- o4-mini-deep-research -> grok-4-fast
- grok-4-fast -> gemini-flash

### ABORT
- Cancel the operation
- Use when: Cost is unacceptable
- Result: Partial results may be available

## Session Cost Tracking

Track cumulative costs during a session:

```
Session Start: $0.00
  + Standard research: $0.005
  + Expert query: $0.01
  + Deep research: $0.15
  ----------------------
  Session Total: $0.165
```

Always report:
1. Individual operation costs
2. Cumulative session total
3. Remaining budget (if set)

## Budget Protection Layers

Deepr implements multi-layer budget protection:

| Layer | Default | Hard Cap |
|-------|---------|----------|
| Per Operation | $5 | $10 |
| Per Day | $25 | $50 |
| Per Month | $200 | $500 |

## Cost Optimization Strategies

### 1. Start Shallow, Go Deep
Begin with standard research. Only escalate to deep research if needed.

### 2. Use Expert Knowledge First
Query existing experts before triggering new research.

### 3. Batch Related Queries
Combine related questions into single research jobs.

### 4. Set Explicit Budgets
Always specify budget limits for agentic operations.

### 5. Monitor Cumulative Costs
Track session totals and pause if approaching limits.

### 6. Use OPTIMIZE_FOR_COST
When elicited, consider cheaper models for non-critical tasks.

## Cost Estimation Formula

Approximate cost calculation:

```
Base Cost = Model Rate x Estimated Tokens
Research Cost = Base Cost x Number of Phases
Agentic Cost = Research Cost x Autonomy Factor (1.5-3x)
```

## Reporting Costs to Users

Always include in responses:
- Estimated cost before operation
- Actual cost after completion
- Cumulative session total
- Budget remaining (if applicable)

Example:
```
Research complete.
- This operation: $0.15
- Session total: $0.32
- Budget remaining: $4.68
```
