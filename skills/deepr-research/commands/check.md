# /check Command

Check the status of a research job or list all active jobs.

## Syntax

```
/check [job_id] [--verbose] [--follow]
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `job_id` | No | - | Specific job ID to check (lists all if omitted) |
| `--verbose` | No | false | Show detailed progress including current task |
| `--follow` | No | false | Subscribe to updates until completion |

## Examples

```
/check                                    # List all active jobs

/check abc123-def456                      # Check specific job

/check abc123-def456 --verbose            # Detailed status

/check abc123-def456 --follow             # Subscribe until complete
```

## Job Phases

| Phase | Description | Typical Duration |
|-------|-------------|------------------|
| `QUEUED` | Job submitted, awaiting processing | < 1 min |
| `PLANNING` | Creating research plan | 1-2 min |
| `EXECUTING` | Active research in progress | 3-15 min |
| `SYNTHESIZING` | Combining findings into report | 1-3 min |
| `COMPLETE` | Results ready for retrieval | - |
| `FAILED` | Error occurred during execution | - |
| `CANCELLED` | Job cancelled by user | - |

## Status Response

Standard response:
```
Job: abc123-def456
Phase: EXECUTING
Progress: 65%
Cost: $0.12
Time: 4m 32s
```

Verbose response (`--verbose`):
```
Job: abc123-def456
Phase: EXECUTING
Progress: 65% (3/5 tasks complete)
Current: "Analyzing market trends"
Cost: $0.12 / $1.00 budget
Time: 4m 32s
Model: gpt-4o
Sources: 12 consulted
```

## Resource Subscriptions

For efficient monitoring, use resource subscriptions instead of polling:

| Resource URI | Content |
|-------------|---------|
| `deepr://campaigns/{id}/status` | Phase, progress, cost |
| `deepr://campaigns/{id}/plan` | Research plan details |
| `deepr://campaigns/{id}/beliefs` | Accumulated findings |

Token efficiency:
- Polling: ~500 tokens per check
- Subscription: ~150 tokens per update
- Savings: 70%

## Actions

| Action | Command |
|--------|---------|
| Cancel job | `deepr_cancel_job(job_id)` |
| Get results | `deepr_get_result(job_id)` when COMPLETE |
| List all jobs | `/check` with no arguments |

## Error Handling

| Error | Resolution |
|-------|------------|
| `JOB_NOT_FOUND` | Verify job ID; jobs expire after 90 days |
| `JOB_EXPIRED` | Results no longer available |
