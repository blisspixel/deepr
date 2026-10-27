# Evidence selection and delivery across briefing and consult packing

Status: #258 comparison completed as evaluated/rejected, 2026-10-21. The shipped
briefing selection and dependency-aware consult packer remain, with the committed
compatible repairs from `f204303` and `1d5ee`. Later advice-strength, query-group
ordering/reservation, soft-target and cue-placement proposals below are rejected
and unshipped. Their design and trial history remain evidence. Target v2.50.44
exact-main CI and public-install validation remain pending. This continues the
[consult evidence delivery](consult-evidence-delivery.md) repair (#227, #238);
it does not qualify general answer quality or S0.

## Problem

Evidence passes two bounded boundaries before an answer: study findings into
the brief synthesis prompt, and positions, findings and passages into the
consult synthesis prompt. Both boundaries could lose material without a
structured record of what was lost.

Briefing took the first 120 findings in outcome order and clipped every field
to 600 characters. Outcome order is lens order, and `contention` is fifth of
the eight default lenses, so the cap was a lens policy rather than a size
ceiling. The contention note counted the whole study, including findings the
prompt never carried. A clipped field could lose the trailing condition that
made it true and present the prefix as complete.

Consult packing interleaved positions and findings by list index, so a
position could be kept while its cited evidence was dropped and the adjacent,
unrelated finding was kept instead. The omission notice listed every omitted
block name after reserving 120 characters, so the notice itself could exceed
the bound.

A stored citation, a retrieved excerpt and an excerpt delivered to the
answering model are different states. The record must keep them apart.

## Contract

One rule at both boundaries: select whole units by an explicit, named policy;
mark anything shortened; record presented, omitted and shortened identities
next to the exact prompt hash; and never let a count or a notice imply more
coverage than was delivered. The full study and the full consult packet stay
the drill-down artifacts. Mechanical checks cover identity, citation
dependency and length. Whether a particular disagreement is material, or
whether an answer used the evidence well, needs reviewed or calibrated
semantic judgment and is not decided here.

### Briefing selection (implemented)

`experts/brief_selection.py` owns the choice:

- **Complete findings within a declared prompt bound**
  (`lens-balanced-complete-findings-v2`). Consider one finding per lens in
  turn, keeping each lens's order, and admit at most 120. Admit every eligible
  payload field and the unverified-support annotation together, or omit the
  entire finding. Render admitted findings in study order. A long field that
  fits remains complete, including its final condition. Do not extract a
  favored sentence or summarize a field to make it fit.
- **Exact envelope admission.** The production serialization ceiling is
  60,000 characters, including all instructions, identities, prior questions,
  notices and finding text. Callers can declare a smaller positive allowance;
  they cannot raise the ceiling. This new explicit ceiling does not change
  backend context, output, call or time limits and does not prove token fit.
  Recompute the actual complete prompt during admission. If mandatory framing
  cannot fit, record a pre-dispatch refusal with zero completion calls.
- **Receipt.** `ExpertBrief.synthesis_input` records the policy, study
  fingerprint, per-finding content hashes, total findings, presented and
  omitted ids, each omission's reason (finding cap or prompt characters), the
  declared prompt allowance, contention presented versus total, and the exact
  prompt hash and length. A drill-down must match the retained study identity
  and finding content hash; positional ids alone are insufficient. The
  originating caller retains its actual study artifact. The synthesis has no
  automatic tool to fetch omitted material. Failed and unparseable syntheses
  retain receipts too. `generated_from_findings` keeps its study-total meaning.
  Historical v1 shortening receipts remain readable; unknown historical
  delivery is never reconstructed as complete.
- **Prompt honesty.** The contention note counts contention findings actually
  shown and says how many more exist. When findings are omitted the prompt
  says how many were shown and forbids claiming the whole study was
  considered. Citations to an id the synthesis was not shown are dropped
  from positions, anticipated questions and orientation statements, like any
  other unknown id. The brief's limitations state omissions and
  shortening.

Comparison before choosing (structural only, `.agent/evidence-delivery-2026-10-19/`),
synthetic studies over the default lens order with a 120-finding cap:

| Study shape | Findings | Prefix: lenses, contention shown | Balanced: lenses, contention shown |
|---|---|---|---|
| 4 chunks x 3 per lens | 96 | 8/8, 12/12 | 8/8, 12/12 |
| 10 chunks x 3 per lens | 240 | 4/8, 0/30 | 8/8, 15/30 |
| 20 chunks x 4 per lens | 640 | 2/8, 0/80 | 8/8, 15/80 |
| 60 synopsis, 10 each other | 130 | 7/8, 10/10 | 8/8, 10/10 |
| 100 synopsis, 30 orientation, 8 each other | 178 | 2/8, 0/8 | 8/8, 8/8 |

Below the cap both policies present the same set. Every retained study found
on this workstation had at most seven findings, so the cap has not been
observed to bind in a real study here, and real-study frequency is unmeasured.
This table shows coverage of lens labels, not better briefs. The first semantic
contrast failed acceptance; a later briefing review compared both policies
under the same allowance. The bounded V5 briefing
warning/renewal result is separate from the rejected consult candidates and
shared brief-metadata defects; see the [completed follow-up](../validation/evidence-followup-2026-10-21.md).

### Consult packing (implemented)

`experts/consult_prompt.py` packs `PacketBlock` units. A block carries a key
(`position:<rank>`, `finding:<id>`, `reference:<sha>` or a section name),
the finding ids a position cites, and the passage hashes it contains. Plain
string blocks from other perspective sources still work.

- **Dependency-aware groups.** Each position is followed by the findings it
  cites, in citation order, not by whichever finding shares its list index.
  Evidence already placed for an earlier position is not repeated. Uncited
  findings follow all groups.
- **Stances first, then evidence.** At the first position, room is reserved
  for every stance that fits, each with its worst-case partial-support line.
  Evidence then fills the remainder group by group. If a group does not fit
  whole, the stance stays with `Delivered support: partial. Cited evidence not
  in this prompt: <ids>`, naming exactly its own missing evidence, including
  evidence an earlier position could not fit. A stance that cannot be
  reserved is omitted and its evidence may still be offered alone.
- **Delivery manifest.** `build_synthesis_packet` returns the prompt and a
  `deepr.synthesis-delivery-manifest.v1` record, stored as
  `context_delivery.delivery_manifest`. Per expert: source, assembly coverage,
  study fingerprint and binding, budget and delivered characters, and per
  position `complete`, `partial`, `absent`, `omitted` or `no_cited_support`,
  with cited, delivered, omitted-by-limit, unavailable and unresolved finding
  ids. A delivered block counts as support only when the position's citation
  resolved to this study and a read passage, so a reused id from another
  study or an unanchored finding is never `complete`. An omitted position is
  recorded after packing, so evidence delivered on its own is not listed as
  missing. Plus
  delivered and omitted findings, delivered passage hashes and omitted block
  keys. The CLI names each position whose support was not fully delivered.
  Delivery coverage is separate from assembly coverage; neither implies
  entailment or answer correctness.
- **Bounded notice.** The omission notice names omitted blocks (first line,
  at most 60 characters each) only while the whole notice and its separator
  fit the 240-character reserve, then counts the rest. The previous notice
  could list every omitted name after a 120-character reserve, and never
  counted its separator.
- **Proven bound.** A property-based test packs random mixes of positions,
  tiny and huge findings, short and long ids, and budgets, and asserts the
  packed text never exceeds its budget. It found the uncounted separator; a
  deterministic test pins the second case it exposed, where a partial-support
  line naming long missing ids could outgrow the room reserved when shorter
  ids were listed. Room is now always reserved for the longest ids.

Comparison before choosing (structural only, same budgets, 300 seeded random
single-expert contexts per budget, 1 to 6 positions citing 1 to 4 of 4 to 24
findings): positions kept, positions kept with all cited evidence, positions
kept with missing evidence and no flag, and findings delivered.

| Budget (chars) | Positions | Old: kept / complete / silent | New: kept / complete / silent | Findings old / new |
|---|---|---|---|---|
| 2,500 | 1,052 | 758 / 22 / 736 | 888 / 45 / 0 | 453 / 204 |
| 5,000 | 1,058 | 982 / 154 / 828 | 1,058 / 328 / 0 | 1,186 / 1,000 |
| 8,000 | 1,020 | 1,020 / 395 / 625 | 1,020 / 769 / 0 | 2,107 / 2,006 |
| 15,000 | 1,017 | 1,017 / 792 / 225 | 1,017 / 1,010 / 0 | 3,648 / 3,630 |

A group-first variant without the stance reservation was rejected: at 2,500
characters it kept 457 positions against the old packer's 758. The adopted
packer keeps at least as many positions as the old one at every budget and
never leaves missing support unflagged. Its cost is fewer standalone findings
at tight budgets (204 against 453 at 2,500 characters, 1,000 against 1,186 at
5,000), because the reserved stances and partial-support lines take that room.
A single-expert consult has roughly 13,000 characters and three experts about
4,500 each. Whether flagged stances with less loose evidence give better
answers than more loose evidence is a semantic question this table does not
answer. The bounded reviews for #258 and #259 are complete, with rejected
comparisons and no causal memory-benefit claim; their historical results are
retained in the dated validation records.

## Semantic comparison completion (2026-10-20, #258)

Complete the remaining comparison with eight frozen old/current pairs: six
consult packets spanning qualifications, disagreement, and an answerable point
beside an unsupported point, with two finding-order permutations each; and two
briefing comparisons covering lens selection and a trailing condition beyond
the field limit. Keep actual old source bytes, current module hashes, complete
fixture sources, prompts and answer identities. Both arms receive the same
context and output allowance. An old prompt that exceeds its allowance is a
recorded refusal, never silently trimmed or removed from the denominator.
The six unmodified legacy consult fixtures all exceed the bound because of
their omission notice. Retain those non-dispatched inputs separately. For the
semantic selection contrast, use one fixed bounded omission notice on both
arms, preserving every selected stance and evidence byte. This is a declared
common-envelope comparison, not a claim to reproduce unmodified legacy UX.

Use owned local generation and independent calibrated model reviewers.
Calibration controls, label precedence and call/time bounds are fixed before
collecting comparison answers. Keep failed calibration trials, including the
pinned local reviewer that did not pass admission. Review opaque answer ids
against the complete permitted sources and obligations, freeze all labels and
rationales before revealing the arm key, and inspect disagreement and abstention
per case. Label matching on known calibration controls checks reviewer agreement;
it does not replace semantic judgment or establish general judge accuracy.
The independent review service does not expose an exact model snapshot; retain
that reproducibility limit rather than invent a pinned identity or human review.

Preserve the original structural comparisons. A synthetic, model-reviewed
comparison can complete this bounded development question, including a negative
result, but cannot qualify real-domain advice, select a universal packing policy,
or accept S0. A material supported-answer regression requires correction or
rejection of the policy before issue acceptance. Review costs outside the local
attempt ledger remain unknown rather than zero.

Review source inventories include decision sources and distractors, with exact
retained bytes and source metadata. If a reviewer packet omitted material the
generator could see, preserve its first judgments and repair the handoff before
acceptance. Re-review with a distinct artifact while the method key remains
closed; disclose reviewer carryover and any source-scope ambiguity. Do not
rewrite generated answers, silently remove a truncated brief, or count a
reviewed snippet as a completed structured result.

## Alternatives rejected

- **Raise the caps.** Moves the cliff without making it visible, and a larger
  prompt is not better delivery on local models.
- **Recursively summarize long fields.** Adds model calls and creates a new
  lossy layer that would itself need a receipt.
- **Rank findings by word overlap with prior positions.** A lexical check may
  route but not decide which disagreement is material
  ([AGENTIC_BALANCE](../plans/AGENTIC_BALANCE.md)).
- **A new store or event type for the receipt.** The brief and consult
  artifacts already carry study identity and prompt receipts.

## Boundaries

No new database, provider, model call, event-authority migration or automatic
belief update. Existing artifacts and legacy reads keep working. This refines
the S1 delivery boundary in [living expertise](../plans/living-expertise.md);
it does not establish S0-S4 success.

### Follow-up from material answer review, 2026-10-20

The corrected paired trial retained more individual obligations but still
lost a renewal condition after character 600, and one consult exceeded its
180-word request with repetitive guidance. The policy is not accepted on label
counts. Preserve those failed outputs and obtain a separately authorized
prospective comparison after repairs; the original 100-call budget is exhausted.
Non-forecast engineering advice may leave likelihood and forecast-registration
fields empty. A renderer must not call that absence a failure of judgment.
An explicitly registered prediction without likelihood may receive a structural
probability-scoring warning. No lexical rule decides whether advice is true,
safe, contradictory or useful. The one-synthesis-call consult contract remains
in force; an automatic repair would need a separately versioned execution
contract and is not part of this increment.

### Consult response form (one-call increment, 2026-10-20)

`consult_response.py` recognizes one narrow literal format in the original
question: a final positive sentence `Answer in at most N words.` with a
positive integer of at most five digits. Quoted/code-containing questions,
other word-count references and unsupported spellings decline automatic
admission. Their original requirements still reach the model unchanged.
This is a parser for that format, not a general interpretation of user intent.
The exact bounded prompt and its delivery manifest record the admitted form.

Count every whitespace-separated token in the complete visible answer,
including headings, caveats, code and citations. The counting rule is versioned;
it is not a language-aware tokenizer. Preserve an overlong normally completed
draft and its original usage, model/request binding and delivery receipt, mark
`ResponseWordLimit` with `synthesis_status: failed`, and expose the additive
`response_form` receipt in CLI/MCP artifacts and the A2A compact result.
Transport/truncation failures retain precedence. Delivery can still be recorded
when answer form fails; semantic preservation stays unassessed. A compliant
count never qualifies advice. No clipping, extra completion or automatic repair
is admitted. The public maximum remains one synthesis call.

### Advice strength after complete delivery, 2026-10-21 (rejected, unshipped)

Historical V6 proposal: the following design preceded its trial. Its negative
result is retained; the added instruction is not part of the release scope.

The separately frozen 32-answer follow-up preserved the briefing warning and
renewal prerequisite, and all 16 current answers met the literal word cap.
It still failed whole-answer acceptance: a current consult converted a narrow
hosted observation and a self-hosted suggestion into categorical configuration
instructions for every matching hardware profile. The prior sources, answers,
labels and negative decision remain unchanged.

Strengthen the existing synthesis guidance to distinguish source observations,
suggestions and requirements, preserve the limits of an untested recommendation,
and name a useful next check when evidence cannot settle a material unknown.
The model judges these meanings. No lexical rule grades a recommendation, and
no new call, automatic repair, research or write authority is introduced.
The added instructions consume the existing prompt allowance.

A new prospective comparison covers the six affected consult families at both
seeds, with 24 new local calls. Compare the current instruction and packing
bundle against the unchanged legacy selection with its declared common form
and omission-notice adapters; this cannot isolate the instruction's causal
effect from packing. Preserve the unchanged eight prior brief answers and
their actual assembly and whole-answer review as separate component evidence,
with exact producer, input and review bindings. They are not new trial cells.
Freeze fresh primary labels and separate whole-pair reviews before their
respective keys open. The no-material-current-regression criterion remains.

### Query-group delivery after the negative V6 trial, 2026-10-21 (rejected, unshipped)

Historical V7 proposal: the following ordering, reservation and soft-target
changes were tested but not adopted. The shipped dependency packer remains.

V6 reduced overprescriptive configuration advice but omitted the monitoring
passage in a directly supplied, reverse-ordered context. The current answer
then refused a known reference-cluster warning. Preserve that failed trial.
Production preparation already ranks positions; this fixture failure does not
establish the same loss in ordinary production preparation. The final packing
boundary nevertheless accepts explicitly supplied typed blocks without an
ordering guarantee and must defend its own bounded delivery contract.

Carry explicit routing text from each position's question, stance and reason.
Reuse the existing token-overlap primitives for a stable permutation of typed
position/dependency groups, retaining unmatched candidates and all source
objects. Never parse citation prose or source text to infer routing metadata.
Already ranked inputs remain stable; legacy strings retain their order. Shared
findings are delivered once. Duplicate nonempty block keys are structurally
ambiguous and refused before dispatch. Routing is not a relevance or support
verdict.

Protect the first positively matched group's complete available dependencies
when their exact character cost fits after fixed prefixes and omission reserve,
before reserving tangential stances. If it cannot fit, retain the existing
honest partial path. Merely sorting stances was rejected: reserving every
stance first can still starve the leading passage. Do not reserve every
matched group, enlarge the allowance, clip source bytes or filter candidates.

For an admitted literal word cap, use a soft drafting target of five sixths
of the hard maximum, at least one word. The maximum, full visible word count,
failure receipt and one-call contract remain unchanged. Exceeding only the
soft target does not fail admission. This form heuristic needs fresh prompts
in both matched methods; it does not establish semantic preservation.

Verify routing, shared dependencies, exact budgets, no-overlap compatibility
and form limits offline, then prospectively freeze a separate local trial and
fresh independent reviews. Prior negative trials and unchanged brief component
evidence remain separate. No acceptance follows from transport tests alone.

### Narrow form follow-up after V7, 2026-10-21 (rejected, unshipped)

Historical V8 proposal: the following half-target instruction was evaluated and
rejected. It is not a shipped drafting instruction.

The frozen V7 trial repaired known-answer delivery and all individual current
obligations, but all four current eviction drafts exceeded the hard 180-word
limit at 214-219 words. Two legacy counterparts completed within 180 words.
All three whole-pair reviewers found an unresolved tradeoff between current
source fidelity and requested-form loss. Preserve the failed trial and decline
acceptance; correct individual obligations cannot erase that form loss.

Change only `consult_response.response_form_instruction`: draft a brief answer
around `max(1, N // 2)` words, allowing extra room for supported guidance,
conditions and material uncertainty up to the unchanged hard maximum `N`.
The previous five-sixths target did not provide enough headroom in these
observations. Half is a prospective form heuristic, not a measured optimum
or a guarantee. Keep packing and semantic guidance unchanged. A broader prompt
rewrite is unnecessary while the remaining observed defect is drafting length.

Admission still counts the full visible answer against `N`, preserves all
normally completed overlong drafts as failures, and leaves existing transport
failures intact. Exceeding the soft target alone never fails admission. The
literal parser, token/time/spend bounds and one-call maximum stay unchanged.
Clipping, retries and another completion remain excluded. Smaller targets can
lose useful qualifications, so a separate frozen 24-call comparison must review
complete answers, including every failure, with unchanged sources, questions,
rubric and material-regression gate. Prior brief evidence remains separate.

### Isolate form-cue placement after V8, 2026-10-21 (pilot rejected)

Historical prospective design: the following four-call pilot completed before
the final decision below. Its string-only transform was never shipped.

V8 still produced two current forward eviction drafts of 242 and 199 words
against a hard 180-word request, while their legacy counterparts fit at 173
and 177. Q2 judged the current answers materially worse; Q1 and Q3 retained
source-fidelity versus form tradeoffs as uncertain. Preserve the negative.
The current four eviction prompts were byte-identical after packing. Their
same-seed saved requests nevertheless returned different drafts; these are
repeated executions, not distinct delivered-order conditions or deterministic
replay. A smaller numeric target alone has not established a repair.

The existing 90-word drafting cue occurs once before the evidence, more than
4,000 characters before the answer boundary. The hard 180-word request already
occurs near the end, so instruction placement remains a hypothesis, not an
explanation established by the failed drafts. Test only relocating the same
single form cue to the end, transferring its existing two-newline separator.
Preserve total characters and every other prompt byte, including source bytes,
question, general meaning guidance and omission notice. Nonadmitted questions
retain their existing prompt. Do not change target arithmetic, parser, hard
maximum, full-draft failure handling, context allocation or one-call authority.
Duplicating instructions, deleting semantic safeguards and another scalar
reduction would add confounds without resolving the observed failure.

Before editing product source or scheduling another full comparison, freeze a
separate four-call, 1,800-second local diagnostic pilot. Reuse one exact current
V8 eviction prompt, since the order variants are identical. Compare leading
and trailing cue positions at the two existing seeds with fresh calls in both
arms, fixed model digest, generation settings, 6,500 characters, 1,024 output
tokens and 600 seconds per call. Freeze balanced order, all input hashes and
criteria before generation. No retries, replaced failures or paid API calls.
Keep the separate append-only ledger and every complete raw draft, including
failures; the prior 204 comparison attempts remain immutable. A full pilot
would bring this task's native total to 208.

Independent calibrated reviewers must inspect full answers and the retained
world for loss of supported guidance, scope, mechanisms and useful uncertainty.
Their prior calibration and experiment exposure are disclosed; this pilot does
not require or claim fresh reviewer calibration or policy acceptance. Freeze
judgments before revealing its position key. Both trailing drafts must meet the
unchanged hard cap without apparent material loss or unresolved tradeoff before
considering a product implementation and separately frozen full confirmation.
A poor or ambiguous pilot stops this candidate; do not repeat it until it passes.
Even a successful pilot is only development evidence on one reused prompt,
with runtime variability and unknown review-service/hardware costs. It does not
qualify a policy, release, general answer quality or S0.

### Final decision after the placement pilot, 2026-10-21

All four fresh calls returned within the separate 1,800-second bound, without
retries. Both trailing-cue answers used 119 words; both leading-cue answers
used 199 and failed the unchanged 180-word cap. Both calibrated reviewers
judged both pairs uncertain and froze all four judgments before the position
key opened. Review reused their disclosed V8 calibration and answer exposure;
the actual prompts exposed cue placement, so key withholding did not make
condition identity uninferable.

The shorter drafts flattened a limited hosted observation and self-hosted
suggestion into conflicting recommendations, omitted memory-pressure and
validation context, and included separate Windows advice. Leading drafts
retained more qualification but failed the requested form. The predeclared
no-material-loss-or-unresolved-tradeoff progression criterion was not met.
Stop the placement candidate and reject the uncommitted V6-V8 consult changes.
Do not implement the transform or repeat the pilot in search of a pass.

Release scope retains the committed `1d5ee` source and compatible `f204303`
repairs, including the shipped dependency packer, complete briefing admission,
full-draft form failures and generation identity. It excludes the tested extra
group ordering/reservation, soft targets and added advice-strength instruction.
The original trials and all V5-V8 negatives remain unchanged. Four pilot calls
bring the task to 208 native attempts at `$0` direct provider API cost; hardware
and independent review-service snapshot, usage and cost remain unobserved.

This completes the bounded #258 comparison as evaluated/rejected and #259 as a
measurement without a memory win. A positive candidate result is not a release
requirement for the retained compatible repairs. The v2.50.44 release and issue
acceptance records own exact-main and public-install validation. Word adherence, brief judgment
metadata and S0 remain active in ROADMAP. See the
[final evidence record](../validation/evidence-followup-2026-10-21.md).

### Literal form-parser hardening after CodeQL, 2026-10-21

Exact candidate `821daba5` failed CodeQL on the new literal-cap parser
(`py/polynomial-redos`, alert #247). The scanner flags the unbounded
whitespace branch in a search over the caller question. The preceding
punctuation lookbehind may already prevent overlapping whitespace matches;
no exploitable slowdown is claimed from the alert alone. Remove that
ambiguity by matching only the fixed final directive with a bounded numeric
field, then checking the preceding whitespace and sentence terminator
explicitly. This is an equivalent syntax boundary, not a meaning heuristic.

Keep every supported/refused directive, quote/code refusal, hard word count,
full-draft failure, prompt instruction and one-call behavior unchanged. Test
long whitespace, adjacent text, leading indentation, alternate sentence
terminators and malformed numeric fields. Compare both parsers over a fixed
large synthetic string matrix without inference. The prior failed scan is
retained; exact revised-head CodeQL must pass. Historical semantic recipes
remain immutable; the final release recipe binds the hardened parser
separately and does not promote the rejected consult candidate.

### Source observation and excerpt representation repair, 2026-10-27

This is a representation repair from a read-only trace of the reviewed
[2026-10-25 brief replay](../validation/brief-clarification-2026-10-25.md)
and the prepared-consultation trials. It changes what reaches the model and
the reader. It is not semantic acceptance: no replay was run, nothing here
shows that answers or briefs improved, and the residual defects stay open in
ROADMAP until a prospectively frozen review says otherwise.

The trace classified several defects as representation faults that left the
model to fill gaps:

- **Undated stored passages (B1, P1).** `CorpusEntry` records `fetched_at`
  and `publisher`, but consult passages were labelled only by origin and sha.
  The formed context now carries a defaulted `source_observed` mapping (sha to
  recorded fetch time and publisher). Packet passages, synthesis finding and
  reference blocks, the CLI grounds view and the shared perspective payload
  render `origin; publisher; retained copy fetched <time>`. Blank values
  render as `publisher unrecorded` and `retained copy fetch time unrecorded`;
  nothing is inferred from source text or origin keys. The notice gains one
  line scoped to stored copies: "Stored expert sources: retained copies
  fetched <first> to <last> (unrecorded for K of N); stored research was not
  re-checked". A fetch time is when bytes were retained, not when their
  subject was last true. With a prepared layer the line follows the
  preparation notice and adds "This line covers stored sources only; prepared
  observations state their own times." An earlier draft said "fetch time
  unrecorded for all N retained source(s) in this context; nothing newer was
  checked"; in a local prepared trial the preparation model read that as
  covering the whole context, recorded an unrecorded-fetch-time assumption,
  and the answer repeated it although the prepared observations carried
  their own times. The rewording fixes scope only. The scoped labels cost 120
  packet characters and 302 synthesis-block characters on the replay study
  with five undated sources. Contexts
  captured before the field existed restore with an empty mapping and keep
  their original rendering, so the capture rendering check in
  `preparation_context.py` still holds; that module is unchanged.
- **Publisher counts from origin identifiers (B7).** Brief provenance counted
  distinct origin keys and called them publishers, including over blank
  publisher metadata. Positions now render `N source(s) from M origin
  record(s); publisher recorded for K`, with a defaulted
  `publisher_recorded_sources` count. Legacy positions read it as `None` and
  render "publisher not counted in this record". The single-origin flag, the
  consult line, the integrity warning and the credibility note now say origin
  record. The flag's arithmetic is unchanged.
- **Qualifiers only in anchors (B2, B4, B5).** Brief synthesis saw each
  finding's lens paraphrase but not the literal excerpts it was grounded on.
  Each finding's recorded anchors that are wholly contained in a retained
  source the finding cites (whitespace-tolerant, case-insensitive, every word)
  are now shown as the matched source text in the source's casing, never as
  the model's recorded anchor. Study grounding probes only an anchor's first
  400 characters, so reusing it for display would have shown an invented
  continuation of a real prefix as source text; the shared grounding rule
  itself is unchanged. Excerpts appear in recorded order, within 900
  characters per finding, JSON-quoted inside the same untrusted-content
  boundary the study prompt uses, and keyed to an `EXCERPT SOURCES` legend
  carrying origin, recorded publisher and recorded fetch time. The sanitizer
  may neutralize directive-like phrases inside them. Locating bytes is
  provenance; it does not decide that an excerpt supports the finding.
  Unlocated anchors are counted, not shown.
- **Falsifiers that ask for documents (B3) and overfilled history (B1).** The
  brief prompt now asks for an observation or result about the same mechanism
  under the same scope; a document asserting or disclaiming a guarantee is not
  such an observation, and a result over tested configurations cannot by
  itself overturn a stance scoped to all of them. It asks that tested
  configurations, platforms and conditions stay in the stance and that a test
  value is not called a default unless the source does. The change lens now
  states the earlier state only when a source states or dates it, and
  otherwise says it is not stated. The 2026-10-25 clarifications (forecast
  versus standing advice, same-claim revision conditions, no invented history)
  are kept. Wording is guidance to the model; no code checks the meaning of
  the returned falsifier or history.

**Admission order.** Complete findings are admitted exactly as before
(lens-balanced, whole units, exact envelope). Excerpts are then added finding
by finding, in the same lens-balanced order, only while the whole prompt fits.
An excerpt never displaces a finding. The receipt records the excerpt bound
and, per presented finding, how many located excerpts were withheld and why
(`excerpt_chars` for the per-finding bound, `prompt_chars` for the prompt
limit); `limitations()` reports them. Older receipts read with empty defaults.
An excerpt-inclusive unit admitted in the original single pass was measured
and rejected: on the retained 45-finding replay study it pushed eight findings
out at the 60,000-character ceiling.

**Measured on the retained replay study** (45 findings, five sources with
blank publisher and fetch metadata; offline, no model call). The previous
prompt was 33,034 characters with all 45 findings. The revised wording adds
977 characters (34,011 without excerpts). With excerpts the prompt is 59,961
characters: all 45 findings presented, 188 of 190 anchors located and 1
unlocated. The untrusted-content fencing costs room, so excerpts for 7
findings (27 excerpts) are withheld: 6 findings by the prompt limit and 1
excerpt by the per-finding bound, each recorded in the receipt. Under a
smaller declared allowance the added wording alone admits fewer findings (36
rather than 39 at 30,000; 14 rather than 16 at 20,000), each recorded as
before, and excerpts are withheld first.

Consult and MCP share these builders, so their delivery stays identical. No
consult path writes canonical state, and transaction, capture and conflict
protections are unchanged. Structural tests assert presence of dates,
publishers, unrecorded markers, legends, receipts and legacy reads; they make
no claim about answer quality.
