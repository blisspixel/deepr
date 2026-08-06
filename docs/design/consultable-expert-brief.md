# The consultable expert brief

## The problem

A Deepr expert could report what it read. It could not be consulted.

Study produces findings about material. Findings are the right output for a
lens, and the wrong output for a conversation. Nobody wants 56 findings; they
want to know where the field stands, which part of their question is already
settled, what the expert thinks, and what would change its mind. The gap is not
volume, it is that no stage ever formed a view.

The brief is the one stage allowed to form one. That makes it the stage most
able to mislead, so its shape is constrained rather than free.

## Why synthesis is allowed here and nowhere else

An earlier version of this design ruled synthesis out, citing evidence that
an orchestrator which summarizes and rebroadcasts collapses diversity. That
conflated two different operations.

The finding is about lenses influencing each other *before* they have spoken
independently. Post-exposure agreement is contaminated: models conform to a
stated majority more when uncertain in their own prediction, shift from correct
to incorrect answers in response to peer reasoning, and treat
reasoning-*shaped* presentation as persuasive regardless of validity. Multi-
agent debate often degrades accuracy over rounds for exactly this reason.

Synthesis strictly *after* independent generation is a different operation and
does not have this failure mode. So the rule is ordering, not prohibition:
lenses never see each other; the brief sees all of them, once, at the end.

## The four structural rules

These are enforced in types, not in prose instructions, because a prompt rule
is a request and a type is a constraint.

### 1. A position carries its own falsifier

`Position.would_change_my_mind` has no useful default. A stance with nothing
that would overturn it is an assertion, and the render says so in those words.

A falsifier must name something observable. "If new evidence emerges" cannot be
checked, so it cannot overturn anything, which makes it an immunisation
strategy wearing the costume of rigour. `falsifier_is_decorative` flags the
formulaic shapes. It is a heuristic and deliberately warns rather than rejects:
the cost of a false positive is a visible note, the cost of a false negative is
a brief that looks falsifiable and is not.

### 2. Dissent survives

Every intelligence post-mortem examined found the correct answer already
present in the system and smoothed away during aggregation. The Iraq WMD NIE
failure was not the absence of dissent; the State Department's alternative view
existed, and lived below the key judgments behind a page reference the summary
reader never reached. Placement was the failure.

So `unresolved_dissent` renders inline with the position it qualifies, never in
a trailing section. And a brief where *no* position records any dissent is
itself flagged, because that is what averaging looks like from the outside.

### 3. Likelihood and confidence never share a field

How likely a claim is to be true, and how sound the basis for that estimate is,
move independently. A well-evidenced claim can be a coin flip. A thinly
evidenced one can be near-certain.

Intelligence, climate and clinical standards all require this split
independently, and all three record harm from products that collapsed it. The
clinical case is the sharpest: high-quality evidence routinely supports a weak
recommendation when benefit and harm are closely balanced, and low-quality
evidence supports a strong one when a safe alternative exists.

`likelihood` is a closed vocabulary with numeric bands. `confidence` is high,
moderate, or low, with its basis stated separately. They render on separate
lines.

The bands print inline with the word, every time. Readers hold verbal
probability terms to a different scale than authors do, and publishing a
glossary does not fix it: given the guidelines in hand, readers still
reconstruct "very likely" as roughly 65 to 75 percent where the author meant 90
or above. A legend elsewhere is a legend nobody opens, so the number travels
with the word.

### 4. A position may decline to resolve

`resolution` is `single`, `conditional`, or `irreducible`.

Without this, a required stance field guarantees invention whenever the
findings genuinely conflict, because the schema demands an answer and the model
supplies one. Making "these did not reconcile" a first-class value is the only
way to stop that. The prompt says to prefer it over inventing agreement.

An `irreducible` position with no recorded dissent is a contradiction and is
flagged: something must have failed to reconcile.

## Evidential depth, not citation count

Counting citations is the wrong measurement. Five sources restating one
publisher is one publisher's authority, however many pages it came from.

The failure has a name in three fields that each discovered it separately.
Intelligence calls it circular reporting, and it produced both the Niger
uranium forgeries and Curveball, of whom an official said he "had really
provided 98 percent of the assessment" behind a judgment that read as
multiply-sourced. Bibliometrics calls it amplification, measured in a complete
242-paper citation network where reviews and opinion pieces were cited as
though they were data and a hypothesis became fact through citation alone.
Systematic review calls it the studies-not-reports rule.

So each position reports `supporting_documents` and `distinct_roots`, and
`is_single_origin` marks the several-sources-one-publisher shape inline, next
to the position it undermines. That flag is the highest-value check here.

Two related base rates worth holding: roughly a quarter of citations in
published medical literature do not support what the citing paper says they
support, and deployed generative search engines fully support only about half
of their generated sentences. A pipeline that reports zero citation problems is
broken, not clean.

## Anticipated questions must include one that attacks

The highest-value thing a briefer carries is a prepared answer to the question
you are about to ask. The failure mode is generating questions by turning the
brief's own assertions interrogative: those are always answerable, always
on-thesis, and worthless.

So `weakens_thesis` is required on at least one question, and a question set
where nothing attacks is flagged as marketing rather than preparation. The
tradition this borrows from is the murder board and the pre-mortem, both of
which are adversarial by construction.

## Hedging and trust

Hedging does not cost what people assume. Across five experiments with 5,780
participants, communicating uncertainty produced only a small decrease in
perceived trustworthiness, mostly for *verbal* uncertainty. A second pair of
studies with over 12,000 participants found numeric ranges had no effect on
perceived trustworthiness of the source at all.

But the same work found that statements about the mere *existence* of
uncertainty, without quantification, reduce trust in both the number and the
source. "There is uncertainty here" is worse than useless. A band with a basis
is close to free.

This is why the design bans the bare hedge rather than hedging. Every position
states a likelihood or is flagged for not stating one.

## What this does not do yet

Stated plainly, because a design doc that only lists what was built reads as
completeness.

- **No permutation-invariance check.** Position in a long input strongly
  determines what a model attends to, and both attention and *faithfulness*
  follow a U-shape, with content in the middle neglected. Re-running synthesis
  with the finding order shuffled and requiring the positions to be stable is
  the cheapest available check and is not implemented.
- **No atomic-claim entailment audit.** Decomposing the brief into atomic
  claims and requiring each to be entailed by some finding is mechanical, has a
  validated methodology, and is not implemented. Citation verification is
  currently title matching, which catches invented citations but not
  unsupported claims that cite real findings.
- **Position and justification come from one call.** A model's stated reasoning
  does not reliably reveal the actual cause of its stated conclusion: inject a
  biasing feature and answers shift while the explanation never mentions it. So
  the reasoning attached to a position is a plausible account, not a causal
  trace, and separating the two calls is the known mitigation.
- **No dissent-survival test.** Injecting a synthetic minority finding that
  contradicts the majority and requiring it to appear in the output is the
  direct test of rule 2, and rule 2 is the entire point of the product.
- **The brief is not wired into consult.** It writes `brief.md` and prints.
  Nothing consumes it yet, which means talking to a Deepr expert does not yet
  benefit from any of this.

## Related

- `docs/design/expert-v2-architecture.md` - the study pass the brief derives from
- `docs/design/expert-evidence-base.md` - corpus retention and origin identity
- `docs/design/capacity-policy.md` - why this runs at $0 by default
