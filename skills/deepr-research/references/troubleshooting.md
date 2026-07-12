# Troubleshooting reference

## Start with read-only diagnostics

```bash
deepr --version
deepr doctor
deepr capacity
deepr costs doctor
```

Do not print credentials, raw vendor CLI output, private paths, or full provider
responses.

## Capacity and accounting errors

| Condition | Action |
|-----------|--------|
| Provider key missing | Configure the explicitly selected provider or stop |
| Budget insufficient | Return the required hard envelope and ask before changing it |
| Metered expert accounting unavailable | Use local/plan read-only consultation or stop |
| Parent budget unavailable | Split into separately approved bounded jobs or stop |
| Hosted context unavailable | Use local source packs; do not upload or attach vectors |
| Reservation/ledger unavailable | Keep the job queued or blocked; do not dispatch |
| Ambiguous provider failure | Do not resubmit automatically; reconcile settlement first |

Never switch providers as an implicit recovery step. Each metered attempt needs
its own approval and reservation.

## Local Ollama

A scheduled local `busy` result is expected defensive behavior. Report the
retry time and stop. The bounded cadence is 30 minutes, then 2 hours, then 6
hours. Do not sleep for that interval inside the current process and do not
fall through to plan or API capacity.

For `unknown` local capacity, explain that contention could not be proven. Do
not call unknown state free or busy.

## Plan-quota CLIs

- Require explicit non-metered auth mode.
- Treat CLI presence as visibility, not proof of remaining quota.
- Reject API-key-authenticated children as plan capacity.
- Preserve typed timeout, cancellation, exhaustion, and unknown-usage state.
- Copilot is visible/read-only in v2.36.

## Research jobs

Use the job id returned by `deepr_research`. A provider job can take longer than
an estimate. Inspect status or returned resource URIs; do not declare failure
from elapsed time alone. Cancellation may still settle nonzero cost.

If the job reports a malformed result or invalid usage, keep the typed failure
and conservative accounting. Do not fabricate a report from partial metadata.

## Expert state

If an expert answer is stale or low-confidence, surface the gap. Suggest an
explicit local or plan sync/absorb workflow where available. Do not enable
agentic mode or claim that conversation automatically updated beliefs.

If a derived digest or handoff is inconsistent, regenerate it from canonical
structured state. Never hand-edit the derived file as authority.

## Reporting a defect

Include the version, typed error code, sanitized trace/job id, operating system,
and exact read-only diagnostic output needed to reproduce. Keep secrets and
private content out of issues and logs.
