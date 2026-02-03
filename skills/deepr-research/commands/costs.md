# /costs Command

View research spending and budget status.

## Syntax

```
/costs [period] [--breakdown] [--export <format>]
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `period` | No | today | Time period: today, week, month, all |
| `--breakdown` | No | false | Show per-job cost breakdown |
| `--export` | No | - | Export format: json, csv |

## Examples

```
/costs                        # Today's spending

/costs week                   # This week's spending

/costs month --breakdown      # Monthly with per-job details

/costs all --export json      # All-time costs as JSON
```

## Output Format

Standard output:
```
Research Costs (Today)
----------------------
Total Spent: $2.45
Jobs: 8
Average: $0.31/job

Budget Status:
  Daily Limit: $50.00
  Remaining: $47.55
```

Breakdown output (`--breakdown`):
```
Research Costs (This Week)
--------------------------
Total Spent: $12.80
Jobs: 24

Per-Job Breakdown:
  2024-01-15 09:32  abc123  $1.20  "Kubernetes migration analysis"
  2024-01-15 11:45  def456  $0.45  "React performance optimization"
  2024-01-14 14:22  ghi789  $2.80  "Competitive landscape" [agentic]
  ...
```

## Cost Tiers Reference

| Operation | Typical Cost |
|-----------|-------------|
| Standard research | $0.10-0.50 |
| Agentic research | $1-10 |
| Expert query | $0.01-0.05 |
| Tool search | Free |
| Status check | Free |

## Budget Controls

Deepr implements multiple budget safety layers:

| Control | Description |
|---------|-------------|
| Per-job budget | Set via `--budget` parameter |
| Daily limit | Configurable, default $50 |
| Confirmation threshold | Requires approval above $5 |
| Budget elicitation | Pauses job when exceeding estimate |

## Budget Elicitation

When a job exceeds its budget, you receive an elicitation request:

```
Research paused: Estimated $7.50 exceeds budget $5.00

Options:
1. APPROVE_OVERRIDE - Continue with higher cost
2. OPTIMIZE_FOR_COST - Switch to faster/cheaper model
3. ABORT - Cancel and return partial results
```

## Export Formats

JSON (`--export json`):
```json
{
  "period": "week",
  "total_spent": 12.80,
  "job_count": 24,
  "average_cost": 0.53,
  "jobs": [...]
}
```

CSV (`--export csv`):
```
timestamp,job_id,cost,prompt,model,status
2024-01-15T09:32:00Z,abc123,1.20,"Kubernetes...",gpt-4o,complete
```

## Related Commands

- `/research` - Submit new research job
- `/check` - Monitor job progress
