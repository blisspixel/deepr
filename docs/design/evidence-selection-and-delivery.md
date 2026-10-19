# Evidence selection and delivery across briefing and consult packing

Status: briefing selection implemented 2026-10-19; consult packing is the next
increment. Issue: #258. Continues the shipped
[consult evidence delivery](consult-evidence-delivery.md) repair (#227, #238);
it does not reopen it or try to fit the whole library into every prompt.

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

- **Lens-balanced whole findings** (`lens-balanced-whole-findings-v1`). Take
  one finding per lens in turn, keeping each lens's own order, up to 120.
  Every lens that produced anything is represented before any lens gets a
  second slot. The prompt still reads in study order.
- **Marked shortening.** A field over 600 characters is cut at a sentence
  boundary in the second half of the allowance, else at a word boundary, and
  labelled `[shortened: kept of original characters; full text in the study]`.
  The budget is not raised and fields are not recursively summarized.
- **Receipt.** `ExpertBrief.synthesis_input` records the policy, study
  fingerprint, total findings, presented and omitted ids, each shortened
  field with original and kept lengths, contention presented versus total,
  and the prompt hash and length. It is recorded on failed and unparseable
  syntheses too. `generated_from_findings` keeps its legacy meaning (study
  total). A brief without the receipt predates it; what its synthesis saw
  cannot be reconstructed from the brief alone.
- **Prompt honesty.** The contention note counts contention findings actually
  shown and says how many more exist. When findings are omitted the prompt
  says how many were shown and forbids claiming the whole study was
  considered. Citations to an id the synthesis was not shown are dropped,
  like any other unknown id. The brief's limitations state omissions and
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
This table shows coverage of lens labels, not better briefs. The semantic
effect on useful supported positions is untested; a later briefing review
should compare both policies under the same allowance and reject the balanced
policy if it preserves more labels but worsens supported answers.

### Consult packing (next increment)

- Pack each position with the findings and passages it cites as one
  dependency-aware group, deduplicating evidence already placed. If the whole
  group cannot fit, keep the position with an explicit partial-support line
  naming the cited evidence not delivered, or omit it when even that cannot
  fit. Uncited findings follow the groups.
- Return a structured delivery manifest with the prompt: per position
  delivered, partial or omitted support with cited, delivered and missing
  finding ids, delivered passage hashes, and the study fingerprint and
  binding. Assembly coverage (`grounded`/`partial`) is reported separately
  from delivery coverage. Neither implies entailment or answer correctness.
- Bound the omission notice inside its reserve: name omitted blocks while
  they fit, then count the rest. The final prompt stays within the configured
  limit including notices, instructions, question and contributor identities.

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
