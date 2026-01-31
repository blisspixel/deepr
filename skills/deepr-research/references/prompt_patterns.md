# Prompt Patterns Reference

This document provides effective research prompt patterns and examples for getting the best results from Deepr.

## Prompt Quality Spectrum

### Vague (Poor)
```
"Tell me about databases"
```
Problems: No scope, no constraints, no desired output format.

### Better
```
"Compare PostgreSQL and MySQL for web applications"
```
Improvements: Specific topic, comparison structure implied.

### Best
```
"Compare PostgreSQL and MySQL for high-traffic e-commerce applications.
Focus on: connection pooling, read replicas, JSON support, and cost.
Include: performance benchmarks, migration considerations, and recommendation."
```
Improvements: Clear scope, specific criteria, desired outputs defined.

## Prompt Structure Template

```
[TOPIC]: What you want to research
[SCOPE]: Boundaries and constraints
[FOCUS]: Specific aspects to emphasize
[OUTPUT]: Desired format and deliverables
[CONTEXT]: Relevant background information
```

## Pattern Library

### Technical Comparison

```
Compare [OPTION_A] and [OPTION_B] for [USE_CASE].

Focus on:
- [CRITERION_1]
- [CRITERION_2]
- [CRITERION_3]

Include:
- Pros and cons for each
- Performance considerations
- Cost implications
- Recommendation with rationale
```

Example:
```
Compare Kubernetes and Docker Swarm for microservices orchestration.

Focus on:
- Scalability and auto-scaling
- Service discovery and load balancing
- Monitoring and observability
- Learning curve and operational complexity

Include:
- Pros and cons for each
- Resource requirements
- Enterprise support options
- Recommendation for a 50-person engineering team
```

### Strategic Analysis

```
Analyze [DECISION/SITUATION] for [CONTEXT].

Consider:
- [FACTOR_1]
- [FACTOR_2]
- [FACTOR_3]

Provide:
- Risk assessment
- Opportunity analysis
- Recommended approach
- Implementation considerations
```

Example:
```
Analyze build vs buy decision for customer data platform.

Consider:
- Current team capabilities (15 engineers, Python/AWS stack)
- Timeline requirements (launch in 6 months)
- Budget constraints ($500K first year)
- Data privacy requirements (GDPR, CCPA)

Provide:
- Risk assessment for each option
- Total cost of ownership comparison
- Recommended approach with rationale
- Implementation roadmap
```

### Regulatory/Compliance Research

```
Research [REGULATION/STANDARD] requirements for [INDUSTRY/USE_CASE].

Cover:
- Key requirements and obligations
- Compliance timeline
- Penalties for non-compliance
- Implementation checklist

Focus on [SPECIFIC_JURISDICTION] if applicable.
```

Example:
```
Research HIPAA requirements for telehealth applications.

Cover:
- Technical safeguards required
- Administrative requirements
- Patient consent obligations
- Breach notification procedures

Focus on California state-specific additions.
Include compliance checklist for MVP launch.
```

### Market/Competitive Analysis

```
Analyze [MARKET/SEGMENT] landscape.

Include:
- Key players and market share
- Emerging trends
- Competitive positioning
- Market size and growth projections

Focus on [SPECIFIC_ASPECT] for [TARGET_AUDIENCE].
```

### Technical Deep Dive

```
Explain [TECHNICAL_TOPIC] in depth.

Cover:
- Core concepts and architecture
- Implementation patterns
- Best practices
- Common pitfalls

Include code examples for [LANGUAGE/FRAMEWORK].
Target audience: [EXPERIENCE_LEVEL] developers.
```

## Context Inclusion Best Practices

### DO Include:
- Relevant constraints (budget, timeline, team size)
- Technical stack and existing infrastructure
- Industry or regulatory context
- Decision criteria and priorities
- Desired output format

### DON'T Include:
- Irrelevant background information
- Overly detailed history
- Personal opinions as facts
- Ambiguous requirements

## Prompt Refinement Strategies

### When Results Are Too Shallow:

1. Add specific focus areas
2. Request deeper analysis on key points
3. Ask for supporting evidence and citations
4. Specify desired depth level

### When Results Are Too Broad:

1. Narrow the scope
2. Add constraints
3. Specify target audience
4. Focus on specific aspects

### When Results Miss the Point:

1. Clarify the actual question
2. Provide more context
3. Specify what you're trying to decide
4. Give examples of desired output

## Follow-up Prompt Patterns

### Drill Down
```
"Expand on [SPECIFIC_SECTION] from the previous research.
Focus on [ASPECT] with more technical detail."
```

### Pivot
```
"Based on the findings, now research [RELATED_TOPIC].
Consider the constraints identified in the previous analysis."
```

### Validate
```
"Find contradicting viewpoints or risks not covered in the analysis.
Focus on [SPECIFIC_CONCERN]."
```

### Synthesize
```
"Combine the findings from [RESEARCH_1] and [RESEARCH_2].
Provide unified recommendations for [DECISION]."
```

## Quality Checklist

Before submitting research:

- [ ] Topic is clearly defined
- [ ] Scope has boundaries
- [ ] Focus areas are specified
- [ ] Desired outputs are listed
- [ ] Relevant context is included
- [ ] Constraints are stated
- [ ] Success criteria are clear
