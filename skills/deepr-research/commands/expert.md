# /expert Command

Query a domain expert with persistent knowledge and belief formation.

## Syntax

```
/expert <name> <question> [--agentic] [--confidence]
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `name` | Yes | - | Expert identifier (use `/expert list` to see available) |
| `question` | Yes | - | Question to ask the expert |
| `--agentic` | No | false | Enable autonomous research to fill knowledge gaps |
| `--confidence` | No | false | Include confidence scores in response |

## Subcommands

```
/expert list                    # List all available experts
/expert info <name>             # Show expert details and statistics
/expert gaps <name>             # Show known knowledge gaps
/expert beliefs <name> [topic]  # Show expert beliefs, optionally filtered
```

## Examples

```
/expert list

/expert "security-analyst" "What are the OWASP Top 10 for 2024?"

/expert "market-research" "Compare pricing strategies for SaaS products" --confidence

/expert "tech-lead" "Should we migrate to Kubernetes?" --agentic
```

## Expert Resources

Each expert exposes MCP resources for inspection:

| Resource URI | Content |
|-------------|---------|
| `deepr://experts/{id}/profile` | Name, domain, creation date, document count |
| `deepr://experts/{id}/beliefs` | Synthesized knowledge with confidence (0-1) |
| `deepr://experts/{id}/gaps` | Known unknowns with priority ranking |

## Query Patterns

| Pattern | Example | Use Case |
|---------|---------|----------|
| Direct question | "What are best practices for X?" | Specific knowledge retrieval |
| Belief check | "How confident are you about Y?" | Uncertainty assessment |
| Gap exploration | "What don't you know about Z?" | Identify research needs |
| Comparative | "Compare A vs B from your knowledge" | Decision support |

## When to Use Experts vs Fresh Research

| Scenario | Recommendation |
|----------|---------------|
| Domain-specific question within expert knowledge | Use expert |
| Current events or recent developments | Use `/research` |
| Topic outside expert domain | Use `/research` |
| Complex question requiring new research | Use `--agentic` flag |

## Response Format

Expert responses include:
- Answer synthesized from knowledge base
- Confidence level (if `--confidence` flag)
- Source citations from ingested documents
- Knowledge gap indicators (if applicable)

## Error Handling

| Error | Resolution |
|-------|------------|
| `EXPERT_NOT_FOUND` | Run `/expert list` to see available experts |
| `LOW_CONFIDENCE` | Consider using `--agentic` or `/research` |
| `KNOWLEDGE_GAP` | Expert identified gap; suggest research |
