# Consult requested length, 2026-10-18

Scope: the open local consult output-adherence finding. This records
instruction delivery and word counts only. It is not a semantic review, a
quality score or an expert-value claim.

## Cause

The synthesis prompt placed the caller's question directly after a fixed
"Keep the complete answer under 700 words" line and before every evidence
block. The same instructions asked for verification, omissions and
uncertainty. On `qwen3.8:27b`, answers to "In under 100 words" kept the core
answer short and then appended Verification and Omissions sections.

## Correction

The 700-word cap is now an explicit default. A length, format or scope the
question requests takes precedence over it and over every other listed
element, including caveats; the most material uncertainty is stated briefly
inside the answer. After the evidence, the prompt restates the question
verbatim with that precedence. Deepr does not parse the question for a
number and does not truncate or grade the answer; the request reaches the
model as written. Restating the question uses its length twice within the
unchanged 16,000-character synthesis prompt bound.

## Local comparison

The retained synthetic fixture (`.agent/reader-evidence/live_fixture.py`) was
run in fresh isolated roots on `qwen3.8:27b` (`aaee06c39dcf`, Q4_K_M), at
temperature 0.3 and `$0`. No belief file or metered request was involved.

| Prompt | Words (whitespace-delimited) | Under 100 |
| --- | --- | --- |
| v2.50.39 (`c44c0ae58073`, same SHA as the 2026-10-17 retained run) | 243, 233, 233, 190 | 0 of 4 |
| Final candidate (`3735392823f3`) | 72, 169, 150, 93 | 2 of 4 |

Two intermediate candidates (precedence wording only) returned 177, 207, 169,
101 and 127 words; they are retained, not counted as the final result.
Answers, prompts and SHA256 receipts are retained under
`.agent/consult-length-2026-10-18/` (`summary.json`).

## Remaining

Adherence improved but is not resolved: half of the final runs still exceeded
the request, and four runs per arm do not establish a rate. The answers stay
unscored for accountable semantic review, and the roadmap item stays open.
