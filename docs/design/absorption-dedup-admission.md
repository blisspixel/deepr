# Absorption deduplication admission

Status: implementation contract, 2026-10-20.

## Failure and scope

The report absorber bypasses semantic deduplication above 0.92 word overlap,
merges after an unavailable verdict, and restores lexical merging when
`verify_dedup=False`. An offline probe changed 10 USD to 30 USD in a 17-word
claim (0.941 overlap): the verifier was never called and the original claim
was replaced. A second probe with an unavailable verdict also lost the prior
claim. Higher effective confidence cannot establish that two claims agree.

This repair covers report-absorption merge admission and its commit boundary.
It does not qualify the existing model judge, rewrite historical merges,
change ordinary operator-directed belief-store APIs, or adjudicate conflicts.
It adds no provider, background work, spend authority or automatic retry.

## Contract

- Lexical similarity only selects a possible pair. Every proposed absorption
  merge requires an explicit, exactly parsed `SAME` model verdict, including
  near-identical wording. `DIFFERENT`, malformed replies, transport failures
  and disabled verification preserve separate claims. Cost admission failures
  still abort staging before canonical writes.
- Stage the candidate claim/domain and target id/text before awaiting the verdict.
  At commit, hold the existing store mutation lock and confirm that the store's
  actual merge target still has that identity and text. If either claim changed,
  the target disappeared or differs from the verified pair, insert separately. Resolve
  earlier staged ids through the existing committed-id map without granting a
  verdict to changed text. No second lexical match can inherit a verdict.
- An unadmitted merge never combines provenance or confidence. Existing
  contradiction and grounding checks keep their authority. A semantic model
  still decides equivalence; deterministic checks bind the verdict and guard
  the write. Unknown equivalence is not evidence of difference or conflict.
- Keep the existing per-call/run cost and ledger gates. More routed pairs may
  require verification; an insufficient caller ceiling blocks the operation
  rather than widening its budget. Disabling verification makes no dedup calls.

## Alternatives rejected

Raising the overlap threshold still loses one-token price, date and qualifier
changes. Recognizing numeric changes alone substitutes another meaning rule.
Keeping legacy behavior on verifier failure silently authorizes data loss.
Merging whichever neighbor the store finds after verification detaches the
write from the reviewed pair. A new persistence or provider layer duplicates
existing authority.

## Verification and recovery

Regressions must fail on the starting source and cover high overlap, missing
or malformed verdicts, disabled verification, explicit SAME, a different live
merge target, changed candidate or target text, removed targets, and staged-target resolution.
Use synthetic clients and temporary stores only. Verify the normal absorption
result and retained claims/provenance, not just an internal boolean. Run the
focused absorber/store suites and all existing gates. Preserve original trials;
this compatible repair affects future ingestion and cannot reconstruct lost
historical claims. Revert the code if needed; append-only history remains.
