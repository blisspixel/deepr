# TKG longitudinal expert-value pilot (v2.44 offline baseline)

Flagship offline pilot for **Temporal Knowledge Graphs** under the
`$0` expert-value protocol.

## What this is

- Operator-attested blueprint revision is required on the expert first.
- Frozen source worlds live under `artifacts/worlds/`.
- Four arms x five acceptance cases = 20 trials.
- Mode: `offline_extract` (open-book from frozen packs + stored expert packet).
- No models, no network, no metered spend.
- Semantic labels are session-operator structural attestations
  (`identity_verified=false`).

## Reproduce

```powershell
deepr eval expert-value "Temporal Knowledge Graphs" --run-offline-pilot `
  --artifact-root eval/tkg/artifacts `
  --output eval/tkg/expert-value-report.json
```

## Offline baseline results (descriptive only)

| Arm | Correctness (mean) | False support | Stale reuse | Cost |
| --- | --- | --- | --- | --- |
| fresh_research | 4.00/4 | 0% | 0% | $0 |
| static_history | 3.80/4 | 0% | 0% | $0 |
| compiled_expert | 4.00/4 | 0% | 0% | $0 |
| maintained_expert | 4.00/4 | 0% | 0% | $0 |

Interpretation limits:

- Offline extract is open-book on frozen packs, not frontier live research.
- No arm ranking or default policy change is authorized by this report.
- Local-model arms remain optional operator work for a stronger pilot.

## Product lessons already applied

- Consult and handoff disclose recent invalidations as non-current history.
- Dual clocks (valid-time vs transaction-time) and provenance independence are
  acceptance cases, not slogans.
