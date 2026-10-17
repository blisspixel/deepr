# Consult answers from the study it can show

Status: shipped in v2.50.29 as a delivery correction. S0 through S4 stay open.
This note does not claim the expert got better.

## What was wrong

Consult already reads `hold/current` and the study. Three reports still treated
a citation and a boolean as if they were understanding:

- Coverage called a position grounded when `supported_by` was non-empty.
  Finding ids are positional inside one study. A later study can reuse the id.
- Local synthesis used the OpenAI-compatible chat endpoint. That endpoint does
  not carry `num_ctx`, so CPU and iGPU Ollama stayed at a 4096-token context
  while study used 16384.
- `dissent_preserved` was always true. Live items and unknowns were on the
  brief and were not required in the synthesis prompt. Exact placeholder tokens
  such as `false` and `none` rendered as recorded dissent.

## Contract

Grounded means every selected position is bound to this study's fingerprint,
every cited finding exists and has a grounded anchor, and a non-empty retained
passage was read for each of them. Anything else that still carries a position,
finding, or passage is partial. Partial keeps the existing 0.4 packet
confidence so the consult still runs. Uncovered stays 0. Word overlap is not a
verdict. New briefs from `assemble_brief` store the fingerprint. A brief
without one, including older files, stays unbound.

Local synthesis calls the native Ollama runtime with the selected model,
`num_ctx` 16384, `think: false`, temperature 0.3, and the existing 8000-token
output cap. It does not swap models or drop evidence to fit 4096. The synthesis
prompt character cap is unchanged. A block that does not fit is named in the
omission line, including a block skipped in the middle. Plan-quota synthesis
stays on the OpenAI-compatible shape. Metered providers still fail before
dispatch.

`dissent_preserved` is structural. It is true when every recorded caveat is in
the delivered prompt, or when none was recorded and synthesis completed,
truncated, or skipped. It is false when synthesis did not deliver the prompt or
a recorded caveat was omitted. `reviewed_preservation` stays `unassessed`.
Empty disagreements are not consensus. MCP and A2A accept this shape and reject
a bare true.

## Out of scope

This does not run S0, attach preparation to consult, admit a proposal into
beliefs, or let MCP, schedules, or consult close a claim. Absorb still extracts
atomic claims. Stance, concept, hypothesis, and agenda readers still have no
consult caller.
