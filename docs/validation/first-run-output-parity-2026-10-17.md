# First-run output parity validation, 2026-10-17

Scope: #237, #232 and #233. No paid API or model call is needed to inspect
these commands. The unit socket guard remains enabled.

The installed v2.50.31 candidate reproduces a new quota lock from an empty
working directory, missing doctor/list JSON options and a tool preview without
its disabled-web reason. Five regression cases fail against main `6653aa3d`:
capacity human and JSON writes, doctor/list JSON absence, and the missing-model
consultation refusal's empty JSON stream. The same cases pass with the repair.

Focused checks cover unchanged writer locking and durability, populated and
absent read-only quota stores, partial append refusal, complete legacy final
records without a newline, per-user banner placement, preview/human reason
parity, diagnostic counts, missing local capacity and validation refusals.
Actual doctor and expert-list JSON outputs validate against published schemas.
No schema, spend boundary or coverage gate is weakened. Existing complete
malformed quota rows retain their compatibility behavior; an incomplete final
row now refuses inspection instead of returning an older quota observation.

The blocking strict islands, source formatting and lint, file-size and
complexity ratchets, and paid-API boundary checks pass. Full coverage, package
and exact-head CI results are recorded with the release. Logs and before/after
CLI outputs are retained under `.agent/reader-evidence/` in the release checkout.

The separate native-local diagnostic is not this unit validation or the missing
S0 baseline. Its eight terminal cells comprised three answers and five blocked
cells; twelve worker attempts matched twelve selected canonical ledger events
at `$0`, plus one separate warm-up event. It retained two truncated construction
briefs. A separate larger-output construction trial completed with three further
`$0` attempts. Source inventories, imported code and accepted memory identities
were checked; canonical-expert unchanged status was null, not a verified pass.
No semantic review, successful blinding, OS network confinement or improvement
claim is asserted. These findings remain in the roadmap before another full
rehearsal; the older interrupted trials are not overwritten or reconstructed.
