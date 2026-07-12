# /research command

Submit one bounded research job. Metered batch, campaign, continuation, and
agentic execution are gated in v2.36.

## Syntax

```text
/research <query> [--budget <amount>] [--provider <provider>] [--model <model>]
```

Use an explicit provider, model, and positive budget ceiling. The budget is a
maximum, not a target or fixed quote. Obtain approval before dispatch.

## Workflow

1. Narrow the question to one research job.
2. Preview the exact CLI envelope when a CLI preview is available.
3. Confirm the ceiling with the user.
4. Call `deepr_research` once.
5. Monitor the returned job id or resource URI.
6. Retrieve the report and preserve citations.
7. Report actual settled cost when available.

Do not pass hosted files in v2.36. Use local source packs or compact prompt
context. Do not call `deepr_agentic_research`; its visible adapter fails closed
until parent-run accounting is complete.

## Errors

| Error | Resolution |
|-------|------------|
| `BUDGET_EXCEEDED` | Return the denial and ask before changing the ceiling |
| `BUDGET_INSUFFICIENT` | Show the required bound; do not weaken it |
| `PROVIDER_NOT_CONFIGURED` | Identify the missing explicit provider capacity |
| Capacity/accounting unavailable | Stop or choose an explicit local/plan consult path |

Related read-only commands: `/check`, `/costs`, and `/expert`.
