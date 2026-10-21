# Historical correction-diagnostic review, 2026-10-20

Scope: #275, a review-continuity increment for #259. This verifies access to
retained artifacts after a recipe-code update. It does not review answers,
repeat inference, change the frozen cases or qualify S0.

## Reproduction and boundary

The retained 36-answer run from 2026-10-19 still matches the frozen
`correction-survival-v1` case set. Its recorded recipe is
`9d909236d977157010192a2827d910d006b3140912693d5a8b711c0babbe06c8`.
After the routing/accounting repair, the default loader rejects it as produced
by different selection or packing code. A three-attempt synthetic run followed
by a mocked code-hash change reproduces that refusal without inference.

The default `load_run` current-recipe check remains strict. The optional
`expected_recipe_sha256` instead permits inspection against an explicitly
known recorded recipe. It accepts only a full lowercase hexadecimal SHA-256
and must match the retained run exactly. Completion-marker, current case-set,
scheduled-count and prompt/answer file checks still apply. Wrong pins, missing
markers, changed cases, altered files and incomplete denominators refuse.
This does not admit execution reuse or authenticate an arbitrary artifact's
origin. The operator still needs a known experiment record for the pin.

`deepr eval correction-survival-report --run-dir DIR --recipe-sha256 SHA
[--json]` prints a verified report without generating, routing, writing a run,
creating cost state or binding labels. It preserves original code/recipe
identity and separately reports the current recipe and equality comparison.
An equality result is about the recipe bytes, not answer correctness or runtime
compatibility. Re-rendering an older report without these comparison fields
keeps the comparison unknown. A changed case set still needs the original
implementation; this increment does not reconstruct missing case definitions.

## Retained-run check

The locked source CLI's help, JSON output and human output were exercised
against `.agent/correction-survival-2026-10-19/local-d0/` using the full original
pin above. The command verifies all 36 attempts, reports zero reviewed
obligations, preserves the recorded `deepr 2.50.41` code identity, and reports
that the historical recipe differs from current code. All 96 retained files
have identical SHA-256 hashes before and after both commands. The isolated
configured data and cost roots were not created.

The [content-free receipt](artifacts/historical-diagnostic-review-2026-10-20.json)
records the observed identities and checks. Raw artifacts and the existing
36-answer review packet remain local. Answer text was not inspected and the
private assignment key was not opened. Reports are operator artifacts;
reviewers continue using the blinded packet. No labels, quality verdicts,
paid requests or new local model calls were produced.

## Verification

Fourteen regressions failed against the old implementation. The final focused
suite passed 51 checks, including the new historical loader, CLI, legacy report
handling, current diagnostic, local completion and routing-identity tests.
The CLI tests trap generation, local answerer and routing construction and
verify that reports create no configured data root or retained-artifact writes.
A failed synthetic answer remains in the complete three-attempt denominator.

The complete offline unit suite passed 13611 tests with 22 existing
skips in 1002.56 seconds, with 85.69% combined statement/branch coverage.
The independent unchanged 80% coverage gate passed. Credentials and dotenv
loading were disabled and the socket guard remained active. Both strict type
configurations pass on 296 files. Ruff, formatting, file-size and code-health
ratchets, paid API boundaries, documentation consistency and pre-commit pass.
No skip, expected-failure marker, ignore or gate was added or relaxed.

The local full trial above predates the separate #277 dependency repair.
The historical-review implementation and regression bytes remain unchanged
when rebased onto that repaired main. Final acceptance requires fresh CI on
the combined head and its current main base, recorded in #275 and PR #276;
the original retained-run receipt is preserved rather than rewritten.

Receipts and logs are under `.agent/review-continuity-2026-10-20/`; continuity
is in the existing `.agent/reader-evidence/session.md`. No codegraph was
available, so source, callers and tests were traced directly. There is no
provider, dependency, release or spend-authority change. This is an Unreleased
source repair. Semantic review #258/#259, S0 and the retained maintenance
finding remain open.
