# /expert command

Inspect, create, maintain, and consult persistent experts through explicit
works-now capacity.

## Read-only discovery

```bash
deepr expert list
deepr expert info "Security Analyst"
deepr expert health-check "Security Analyst"
deepr expert loop-status "Security Analyst" --json
deepr expert memory-card "Security Analyst"
```

These surfaces inspect structured expert state. A health or validation pass is
not a semantic truth certificate.

## Provider-free creation and maintenance

```bash
deepr expert make "Security Analyst" --local -d "Application security"
deepr expert sync "Security Analyst" --local --fresh-context -y
deepr expert sync "Security Analyst" --local --fresh-context --compile-claims -y
```

Explicit non-metered plan-quota variants work only on documented commands with
`--plan <id>` and the no-surprise-bills auth gate. Do not infer plan capacity
from CLI presence. Copilot is visible/read-only in v2.36.

Scheduled local work may return a durable `busy`/waiting result with a retry
time. Preserve that outcome and do not fall through to plan or API capacity.

## Consultation

Use `deepr_query_expert` only with:

- `backend="local"`, `agentic=false`, and budget `0`; or
- `backend="plan"`, an explicit non-metered `plan`, `agentic=false`, and budget
  `0`.

Use `deepr_consult_experts` for one or several experts. Prefer
`synthesis_backend="local"` or `"plan"`, keep the roster at 10 or fewer, and
preserve dissent. API council synthesis is a separate bounded surface and
requires explicit approval plus a positive budget.

## Derived portability

Expert handoffs, memory cards, digests, OKF bundles, and skill exports are
regenerable views over structured state. Do not hand-edit them as authority.
Import and absorb must pass the verification and explicit apply boundary before
belief state changes.

## Gated in v2.36

Do not advertise or retry these as live metered workflows:

- generic nonlocal `expert make` or `--learn`;
- API curriculum planning, resume, refresh, or synthesis;
- metered `fill-gaps`, route-gaps, reflection, or sync/sync-all;
- paid portrait generation or API consult-quality judging;
- standalone metered `expert chat`;
- `deepr_query_expert backend="api"` or `agentic=true`.

Use local, explicit non-metered plan, scheduled wait, dry-run, history-only, or
read-only alternatives where the command documents them. A larger budget does
not unlock a gated transaction.
