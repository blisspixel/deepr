# Decision review inspection, 2026-10-18

Scope: #228 and the [read-only design](../design/decision-review.md).
These are synthetic record and interface checks, not a review of advice quality.
No model, paid provider or external research call was made by the inspection.

Installed v2.50.34 and candidate v2.50.35 were inspected against the same frozen
fixture. The earlier experience overview returned one active observation and
seven consult metadata fields, without the answer or context. The new review
retained both observations and the original answer/context. Both commands left
the fixture unchanged; the ordinary overview remains short.

The focused suite passes 59 cases across the new packet, CLI, experience join,
consult traces and outcome stores. It includes an original answer followed by
a corrected observation, an unrelated explicitly selected comparison, missing
and ambiguous joins, failed/truncated output, absent legacy receipts, retained
superseded outcomes and the 100-trace bound. Markdown retains an exact JSON
receipt, including embedded fences. Published-schema checks reject semantic
quality authority. A real-store CLI test preserves legacy profile bytes and
all trace/outcome files; a missing expert creates no directories.

The first snapshot-equality fixture constructed two traces independently and
therefore received different event times. It was corrected to reuse the same
frozen record. Existing profile mocks were updated to accept the read-only
constructor option. Three newly introduced type inference errors were fixed
with an explicit case-list type. Failed runs remain retained; no assertion,
schema or gate was weakened.

Strict typing passes for all 291 island files and separately for the new packet
module. The wider baseline remains 196 errors in 60 files, with identical
normalized diagnostics. Lint, format, file-size/complexity/security ratchets,
paid-API boundaries and documentation consistency pass. Package checks pass
57 cases; the candidate wheel and source archive include the dashboard.

A fresh Python 3.13 wheel installation passes MCP checks for both supported
protocol versions, package replacement persistence and the host profile.
Three installed CLI inspections produce Markdown/JSON for a correction and an
unrelated comparison, report a missing comparison, and leave every canonical
fixture file unchanged. The Markdown was read to inspect the original answer,
dated observations, environment, delivered prompt and separate comparison.
Fixture identities and observations are synthetic, not operator evidence about
a real expert's quality.

The full unit suite passed 13,167 tests with 20 existing skips and 85.52%
combined statement/branch coverage. Independent coverage enforcement passed.
Exact-head CI is required before merge. Exact-main artifact checks and public installation are
separate publication gates. Logs, fixtures and failed trials are retained under
the existing ignored `.agent/reader-evidence/` directory. No codegraph was
available; the owning stores, source callers and tests were traced directly.
This inspection does not complete S0 or qualify preparation, revision or advice.
