# /research Command

Submit a deep research job with comprehensive analysis.

## Syntax

```
/research <query> [--budget <amount>] [--model <model>] [--agentic]
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | Yes | - | Research question or topic |
| `--budget` | No | 1.00 | Maximum cost in USD |
| `--model` | No | gpt-4o | Model for research (gpt-4o, grok-4, gemini-2.0-flash) |
| `--agentic` | No | false | Enable autonomous multi-step research |

## Examples

```
/research "What are the leading approaches to quantum error correction?"

/research "Compare React vs Vue for enterprise applications" --budget 2.00

/research "Analyze the competitive landscape for AI code assistants" --agentic --budget 5.00
```

## Workflow

1. **Classify**: Determine research depth needed
2. **Estimate**: Calculate expected cost and time
3. **Confirm**: Request approval if cost exceeds threshold
4. **Submit**: Create research job via `deepr_research` or `deepr_agentic_research`
5. **Monitor**: Subscribe to `deepr://campaigns/{id}/status` for updates
6. **Deliver**: Present results with preserved citations

## Cost Tiers

| Mode | Typical Cost | Time | Use When |
|------|-------------|------|----------|
| Standard | $0.10-0.50 | 5-20 min | Comprehensive single-topic analysis |
| Agentic | $1-10 | 15-60 min | Multi-step autonomous research |

## Output Format

Results include:
- Executive summary
- Detailed findings with inline citations
- Source list with URLs
- Metadata (cost, time, model, sources count)

## Related Commands

- `/check` - Monitor job progress
- `/expert` - Query domain expert instead of fresh research
- `/costs` - View research spending

## Error Handling

| Error | Resolution |
|-------|------------|
| `BUDGET_EXCEEDED` | Increase budget or wait for daily reset |
| `PROVIDER_NOT_CONFIGURED` | Set required API key in environment |
| `BUDGET_INSUFFICIENT` | Specified budget too low for query complexity |
