# Readable expert evidence and perspective attribution

Status: implementation, 2026-10-17. Issues #220, #221 and #229.

The knowledge view currently shows anchor counts without the quoted text, and
an orientation paragraph without its provenance. Consultation then hides the
support and currency metadata and cuts the answer. A reader needs to inspect
what was studied and distinguish it from interpretation before S0 review.

## Contract and boundaries

Add optional `orientation_statements` to the existing brief: each contains
`text`, `origin` (`studied`, `broader_knowledge`, `reasoning`, or `unattributed`)
and `supported_by` finding ids. The briefing model owns the classification.
Code validates the vocabulary and citation identity, never infers an origin
from words or uses matched text as an entailment verdict. New orientation text
is assembled from these statements so the displayed text and its attribution
cannot diverge. Legacy paragraphs remain readable with origin unrecorded.
A malformed statement list cannot silently discard an existing paragraph.

Studied statements link only into the study identified by the brief's existing
fingerprint. Unbound, stale, missing and unanchored support is disclosed, never
relabelled as broader knowledge or verified truth. Both reading and synthesis
carry these labels; regenerating a view performs no model call or canonical
write. No beliefs, spend, model defaults or execution authority change.

Finding pages show recorded anchors, retained source links, recorded match
counts, and a per-anchor literal lookup when retained bytes are available.
Missing bytes or a counts-only record cannot establish which quote matched.
Position pages show the stored confidence label, basis, and linked finding and
excerpt counts. These are uncalibrated recorded signals, not probabilities or
expert grades. Renderer revision participates in the view identity so upgraded
output never overwrites or conflicts with an older immutable view.

The terminal view uses the existing consult payload, answers first, and always
shows Grounds, Support, Currency and Pushback, including absent data and
omissions. It preserves complete text and distinguishes model truncation from
display. JSON retains the same envelope; evidence fields are additive only
where needed to make existing retained data inspectable.

## Alternatives and verification

Do not classify old prose by keyword or ask a new model call on read. Do not
link positional ids into a different study. Do not assign individual match
statuses from aggregate counts. Do not hand-edit generated expert artifacts.

Regression tests cover old/new round trips, invalid origins and citations,
stale study bindings, quoted source text, missing bytes, immutable view
regeneration, consult evidence delivery, piped Markdown and narrow rendering.
An isolated fixture-driven workflow proves inspectability; it does not qualify
semantic advice. S0 and blinded human review remain separate gates.

## Failed first-build continuity (#223)

The formation operation retains failed study candidates without publishing them
as active knowledge. Read its candidate summary for status and health, and use
one formation-first action for retry guidance. A completed formation model may
precede the original profile model only while the recorded final artifacts
still match; explicit operation overrides remain first. No profile migration
or canonical expert write occurs during model selection. Empty consultation
returns nonzero; truncated model output remains labelled and complete as received.
