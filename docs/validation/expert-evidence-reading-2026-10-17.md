# Expert evidence reading validation, 2026-10-17

Scope: #220, #221, #229 and the unimplemented portions of closed #223.
This verifies disclosure, persistence and interface behavior, not advice quality.
No paid API calls or belief admissions are part of this validation.

## Reproduction and regression evidence

On the starting v2.50.30 source (`8793a00c`), three new regression cases fail:
finding pages omit the recorded quote, and both human and JSON consultation
return success when synthesis reports no valid perspectives. The same cases
pass on the candidate. Logs are retained in `.agent/reader-evidence/`.

Focused checks cover complete and malformed attribution, old unattributed
paragraphs, study mismatch, missing source bytes, literal matched and unmatched
quotes, recorded support labels, immutable view regeneration, and renderer
version changes. Citation identity and literal matching do not judge entailment.

A failed first-build fixture records twelve findings with zero anchors and a
model distinct from the original profile. Status, health and next read the
candidate without publishing it, disclose that actual model and counts, and
agree on `expert build NAME --no-discovery`. Completed local formation model
selection is checked through CLI, MCP and A2A, including explicit overrides
and refusal to reuse a model when final artifacts changed or are absent.

Consult rendering is checked at sixty columns, with and without a terminal:
complete long answers, literal untrusted Rich markup, all five sections,
stored-only currency, absent labels, eight dissent items, explicit prompt
omissions, model truncation and no mutation of the saved payload.

## Packaging and release gates

The candidate wheel and source distribution include the packaged frontend.
A clean core-only wheel environment passes the existing Agent Plugin stdio
smoke for both supported MCP eras and the OpenClaw host-profile smoke. These
checks include retained data across package replacement. The blocking strict
islands, lint, formatting, file-size and complexity ratchets, paid-API boundary
and documentation consistency checks are run as part of the release gate.
Full unit-suite and exact-head GitHub CI results are recorded with the release.

## Installed local consult

The clean-wheel CLI completed an isolated consult on `qwen3.8:27b` against a
short synthetic checkpoint note. It returned exit 0, retained the full answer
and exact prompt, displayed all five sections and the attributed source text,
and reported `$0.0000`. No belief file was created. The retained prompt SHA256
is `c44c0ae5807303a01823f653d88f8a7c87ff2eb60ebcbd9411d93d177b5ee68b`;
the answer SHA256 is
`54731ffbc28e8dfed944fdba4946a27803b090b4b3bce6d0a3050a8297a604ca`.
The source, generated view, answer, trace and terminal log are preserved under
`.agent/reader-evidence/live/` and `.agent/reader-evidence/live.log`.

This is delivery evidence with synthetic data, not a semantic qualification.
The model exceeded the requested 100-word answer length. The local attempt
appears in consultation traces but produced no append-only cost-ledger event
in the isolated cost root. No paid request occurred. Both observations remain
follow-ups in the roadmap; this patch does not claim to have repaired them.

## S0 remains open

The September rehearsal record identifies a frozen qwen3.6:27b policy and
three synthetic source worlds with twelve cases. This checkout's configured
reports root is `data/reports`; the archived inputs were not found there.
Installed models include qwen3.6:35b and qwen3.8:27b, not that pinned model.
No substitute model, source world, case inventory or review has been passed
off as the frozen 48-cell baseline. Earlier interrupted trials remain valid
failure evidence. Human blinded review is still required before revealing
arm identities. v2.51 is not promoted by this patch.
