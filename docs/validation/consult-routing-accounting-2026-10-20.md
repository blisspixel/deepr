# Consult routing identity and accounting, 2026-10-20

Scope: the bounded remediation in #259. This validates embedding-space identity,
receipt transport, fallback and latency accounting. It does not review answers,
compare semantic quality, promote default routing or complete S0.

## Reproduction and repair

Two mocked-attestation regressions failed on the preceding implementation:
query digest A followed by document digest B still produced a ranking, and a
later attempt using B silently replaced the earlier A identity. With the repair,
the first case refuses before document dispatch, and the second refuses before
another query dispatch. Both preserve the disclosed lexical fallback. No live
model-tag change was observed or induced.

The existing local embedding seam now shares the first attested digest, resolved
profile and vector dimensions. Query/document inputs keep their distinct roles.
A router reuses one transport client across rankings; empty input constructs no
client. Indexed response parsing remains at the embedding profile boundary.

The diagnostic binds each attempt's configured/effective route, identity,
success/fallback/unused state and local call summaries into its hashed run.
Summaries reference the existing canonical native-local attempt IDs, request IDs,
ledger path and cost-state identity. They retain returned, failed, refused,
cancelled and unsettled calls without input text. Unknown tokens stay null in
these summaries, while legacy ledger token fields retain their existing shape.
Accounting failure cannot produce a successful ranking.

## Deterministic evidence

A controlled clock adds time inside mocked attestation, embedding transport,
packet assembly and answer completion. Two production attempts produce:

| Attempt | Effective route | Routing ms | Answer ms | Total attempt ms |
| --- | --- | --- | --- | --- |
| Initial pinned identity | Embedding plus lexical | 6000 | 3000 | 10000 |
| Changed digest refused | Lexical fallback | 1000 | 3000 | 5000 |

The report totals routing 7000 ms, answers 6000 ms and attempts 15000 ms. It
retains three embedding invocations, including the refused call, with unknown
token usage. Oracle/fresh arms say `not_used_by_arm`. Existing `elapsed_ms`
remains answer-only. Removing the new fields from a legacy-shaped run yields
unknown routing/total times, not zeros. Total attempt time excludes shared
fixture materialization and artifact writes; it is not research wall time.

The focused run passed 125 checks across routing identity, diagnostic/report
binding, existing routing, local embedding and embedding profiles. It includes
changed dimensions, profile mismatch, transport failure, ledger failure before
and after dispatch, cancellation, complete ledger joins, and fallback disclosure
in the actual prompt. Full prompt/answer hashes and completion markers still
verify; existing historical-isolation and review-binding tests remain green.

## User-visible source CLI check

From the activated locked development environment:

```bash
deepr eval correction-survival --output-dir <new isolated directory> --distractors 60 --json
```

With dotenv loading disabled and isolated cost storage, all 36 attempts
completed, no model was called, paid calls were zero, and reviewed obligations
were zero. The JSON report exposes separate timing fields and effective-route
counts: 12 lexical production attempts, 12 oracle and 12 fresh attempts without
finding routing. This is an editable source CLI check, not a clean-wheel or
live embedding-model acceptance result.

## Verification and retained limits

- Complete offline unit suite: 13567 passed, 22 skipped in 538.05 seconds;
  combined statement/branch coverage 85.68%. The independent coverage report
  passed the unchanged 80% gate. No new skip or expected-failure marker was
  added; the socket guard and credential/dotenv isolation remained enabled.
- Strict islands pass with the real Python 3.11 dependency floor and Python
  3.15 promoted dependencies. The ordinary floor command against 3.15 NumPy
  stubs initially stopped on unsupported stub syntax; the documented floor
  interpreter resolved that environment mismatch.
- Ruff, format, file-size and code-health ratchets, paid API boundary audit,
  documentation consistency and diff whitespace checks pass.
- The first full-suite run was interrupted after 5092 passes and 11 existing
  skips to add transport-client reuse. It establishes no full coverage result;
  the partial log and subsequent complete run are retained separately.

Scratch receipts are under `.agent/routing-accounting-2026-10-20/`; continuity
is in the existing `.agent/reader-evidence/session.md`. There was no codegraph
available, so routing/backend/diagnostic callers and tests were traced directly
from source. No graph rebuild is claimed.

Earlier local answers and their private review packet remain untouched and
unlabelled. Recipe identity now includes embedding/backend/recorder code; old
runs retain their old identity and are not rewritten to pass a new recipe.
No paid call, new inference trial, provider/dependency change or canonical
expert write was made. #258 and #259 still require accountable blinded semantic
review; #263's replacement S0 decision remains separate.
