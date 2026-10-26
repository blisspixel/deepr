# Communicate the admitted study output budget

2026-10-25. Proposed bounded repair following local development evidence.

The Qwen development synopsis returned 4096 output tokens with
`stop_reason=length`. Its incomplete JSON failed parsing. The second lens
returned a valid empty change result. No usable study, brief, checkpoint,
maintenance or answer followed. All four planned outcomes and both returned
calls remain retained. Earlier development also retains a briefing timeout
with unknown usage. These are separate failures, not S0 acceptance.

The shared study prompt currently asks for source-grounded notes without
communicating the completion's admitted output ceiling. The rehearsal worker
enforces 4096 tokens; CLI and formation backends generally request 16000.
The model must plan its complete JSON response within the actual request
budget. This guidance cannot guarantee compliance or useful findings.

Add optional `max_output_tokens` to the shared study API and prompt renderer.
A supplied value must be a positive integer, excluding booleans. Unknown
budgets remain unknown. Thread the value through the identical renderer used
for dispatch and fingerprinting, and bind it in checkpoint admission. Changed
budget instructions must invalidate prior outcomes and chunks. Preserve the
legacy unknown-budget rendering where no ceiling is known.

Expose a known enforced ceiling as optional `StudyBackend` metadata. Native
local construction applies its exact requested ceiling. The real plan client
currently ignores `max_tokens`, so its metadata must remain unknown; forwarding
an argument to a mock client does not prove transport enforcement.
CLI study and formation pass that metadata; the rehearsal worker passes its
validated policy value. Preserve custom backends with unknown metadata. Do
not infer a budget from a model name, closure internals or an assumed default.
This adds no execution authority to blocked plan or pooled adapters.

Source tracing also found that pooled construction did not forward its
`max_tokens` argument to member builders. Forward the same requested ceiling
to each member, preserving the existing default for legacy callers. This is
requested-value forwarding, not proof of transport enforcement. Report a
common pool ceiling only when actual member metadata supports it; plan,
custom, unknown or heterogeneous member ceilings remain unknown. Keep quota
rollover, fallback eligibility and spend authority unchanged.

The prompt will ask the model to allocate its budget across the full JSON
object, choose useful supported findings and preserve their qualifications.
Code continues to own the numerical limit, schema, accounting and writes.
The model chooses meaning and relevance. There is no fixed finding count,
semantic keyword verdict, clipping, broken-JSON salvage or automatic retry.
Existing complete-response and usable-study checks remain unchanged.

Rejected alternatives are increasing the generation cap to fit this sample,
repeating generation until it passes, salvaging a truncated object, imposing
a topical quota, or adding a rehearsal-only prompt. Shared brief guidance is
outside this repair: the Qwen failure preceded briefing and the earlier brief
failure was a timeout. Rejected consultation drafting candidates remain
rejected; this change communicates an existing transport ceiling.

Verify exact budget delivery and matching prompt hashes, unknown and invalid
budgets, changed-budget checkpoint refusal, caller/backend parity, and retained
malformed-response failure with one call per chunk. Structural tests establish
delivery and admission, not model compliance or semantic quality. Run owning
tests, lint, types, ratchets, full coverage and exact-head CI.

The previous development trial allowance is exhausted. This source repair
does not authorize another run. A subsequent validation needs a new prospective
protocol, new source/runtime identity and independent review, with unchanged
historical evidence. It must remain a separate bounded code-fix validation,
not a resumed run, model cycle or favorable resample. S0 final capacity and S1
implementation gates remain open until their evidence is complete.
