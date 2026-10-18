# Read-only decision review

Status: implementation, 2026-10-18. Issue #228.

An experience overview links observations to a consultation but hides the
retained answer and supplied context. Add a drill-down over the same stores:
`expert review-decision NAME --outcome-id ID` or `--decision-id ID`, with an
optional explicit `--compare-trace ID`. Default output is dated Markdown;
`--json` emits the same packet. Output goes to stdout, so inspection creates no
report, lock, expert record or directory. Operators can redirect a derived
packet to a location they choose.

Reuse the experience trace index and expert-roster join. Duplicate identities,
missing traces, unknown rosters and mismatched experts never expose a guessed
answer. A selected outcome brings all observations with its exact decision ID,
including superseded observations and their original trace links. A decision
with more than 100 distinct trace identities is refused rather than silently
truncated. Identity equality is caller attribution, not proof of applicability.

Each matched consultation retains a frozen copy of the original trace, including
answer status, stop reason, source context, delivered messages, omissions and
failures when recorded. Missing legacy fields stay unavailable. A canonical
JSON hash identifies the record snapshot; it does not certify truth or the
original JSONL encoding. Markdown includes the complete packet as a safely
fenced JSON receipt so its summary cannot lose fields available in JSON.

An explicit comparison shows each question, date and capacity independently.
Mechanical differences concern recorded source identities, context receipts
and delivered messages. Selected context is not assumed to have survived
prompt fitting. These differences make no recommendation-quality, semantic
equivalence or supersession judgment. Still valid, reconsider and unresolved
remain unreviewed prompts for an accountable reviewer. No provider or model
is constructed and no confidence, knowledge or policy changes.

Rejected alternatives: reconstructing an answer from today's expert, choosing
a similar question automatically, judging changes by keywords, introducing a
new memory store, or silently applying a later outcome to earlier advice.
Existing consult/outcome records remain authoritative. S0 and later semantic
preparation/revision gates remain open.

Verification covers an original answer followed by a correction, an unrelated
explicit comparison, duplicate/wrong-expert/missing traces, failed or truncated
answers, absent receipts, superseded observations, input immutability, identical
Markdown/JSON packet contents and CLI filesystem non-mutation.
