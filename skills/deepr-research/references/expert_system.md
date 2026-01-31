# Expert System Reference

This document explains Deepr's domain expert system, including capabilities, philosophy, and usage patterns.

## What Are Domain Experts?

Domain experts are persistent knowledge entities created from documents and research. Unlike simple RAG (Retrieval-Augmented Generation), Deepr experts:

- **Synthesize knowledge** into a coherent worldview
- **Form beliefs** with confidence levels and evidence citations
- **Track knowledge gaps** and can research to fill them
- **Learn continuously** from conversations and new research
- **Maintain context** across sessions

## The Beginner's Mind Philosophy

Deepr experts operate with "beginner's mind" - they:

1. Acknowledge uncertainty explicitly
2. Cite sources for all claims
3. Distinguish between high and low confidence beliefs
4. Admit when they don't know something
5. Can trigger research to fill knowledge gaps

This prevents the hallucination problem common in AI systems.

## Expert Resources

Each expert exposes MCP resources for inspection:

### Profile Resource
`deepr://experts/{id}/profile`

Contains:
- Expert name and description
- Creation date and last updated
- Document sources used
- Total knowledge items
- Specialization areas

### Beliefs Resource
`deepr://experts/{id}/beliefs`

Contains:
- Synthesized beliefs with confidence scores
- Evidence citations for each belief
- Belief formation timestamps
- Contradiction tracking

### Gaps Resource
`deepr://experts/{id}/gaps`

Contains:
- Known knowledge gaps
- Gap priority scores
- Suggested research queries
- Gap discovery timestamps

## Confidence Levels

Expert beliefs use a 5-level confidence scale:

| Level | Score | Meaning |
|-------|-------|---------|
| Very High | 0.9-1.0 | Multiple corroborating sources, well-established |
| High | 0.7-0.9 | Strong evidence, few contradictions |
| Medium | 0.5-0.7 | Some evidence, may have gaps |
| Low | 0.3-0.5 | Limited evidence, significant uncertainty |
| Very Low | 0.0-0.3 | Speculative, needs research |

## When to Query Experts vs New Research

### Query Existing Expert When:
- Topic falls within expert's domain
- Expert has high-confidence beliefs on topic
- Quick answer needed (no async wait)
- Building on previous conversations

### Trigger New Research When:
- Topic is outside expert's domain
- Expert's knowledge is outdated
- Expert reports low confidence
- Comprehensive analysis needed
- Expert explicitly identifies knowledge gap

## Expert Consultation Workflow

```
1. List available experts
   -> deepr_list_experts

2. Check expert profile for relevance
   -> Read deepr://experts/{id}/profile

3. Inspect beliefs if complex query
   -> Read deepr://experts/{id}/beliefs

4. Query the expert
   -> deepr_query_expert(expert_id, question)

5. If knowledge insufficient:
   -> Enable agentic mode for autonomous research
   -> Or trigger manual research to fill gaps
```

## Agentic Mode

When enabled, experts can autonomously:

1. Detect knowledge gaps in their responses
2. Trigger research to fill those gaps
3. Synthesize new knowledge into beliefs
4. Update their worldview
5. Provide enhanced responses

**Budget required:** Agentic mode incurs research costs. Always specify a budget limit.

```
deepr_query_expert(
    expert_id="aws-architect",
    question="How should we design our VPC for multi-region?",
    agentic=True,
    budget=5.0
)
```

## Expert Interview Pattern

For complex topics, "interview" the expert:

```
1. Start with broad question to assess knowledge
2. Inspect beliefs resource for confidence levels
3. Ask follow-up questions on high-confidence areas
4. Identify low-confidence areas for research
5. Trigger targeted research for gaps
6. Re-query after knowledge update
```

## Creating Experts

Experts are created via CLI:

```bash
# From documents
deepr expert make "AWS Architect" --files "./docs/*.md"

# With autonomous learning
deepr expert make "FDA Regulations" --learn --budget 10

# From existing research
deepr expert make "Market Analyst" --from-campaign abc123
```

## Expert Capabilities Summary

| Capability | Description |
|------------|-------------|
| Knowledge Synthesis | Creates worldview from documents |
| Belief Formation | Forms beliefs with confidence scores |
| Gap Awareness | Tracks what it doesn't know |
| Continuous Learning | Updates from conversations |
| Agentic Research | Can research autonomously |
| Citation Tracking | All claims cite sources |
| Export/Import | Shareable knowledge packages |

## Best Practices

1. **Inspect before querying** - Check profile and beliefs for complex topics
2. **Set budgets** - Always specify budget for agentic mode
3. **Trust confidence scores** - Low confidence = consider research
4. **Use gaps resource** - Proactively fill high-priority gaps
5. **Iterate** - Build expert knowledge over multiple sessions
