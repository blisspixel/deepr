# /costs command

Inspect the canonical append-only cost ledger and configured budget ceilings.

```bash
deepr costs show
deepr costs timeline
deepr costs breakdown --period month
deepr costs doctor
```

Treat a budget as a maximum. Do not derive authorization from an average or a
historical example. Use the current exact preview for the selected provider,
model, tools, and request ceilings.

The ledger distinguishes actual provider-reported settlement from conservative
full-bound settlement. A `$0` local or non-metered plan event can still consume
hardware time, subscription quota, or credits outside Deepr's dollar ledger.

If `costs doctor` reports malformed history, conflicting idempotency, or a
durability problem, stop paid dispatch. Never delete or rewrite ledger entries
to make a budget check pass.

See [cost guidance](../references/cost_guidance.md) for the transaction rules.
