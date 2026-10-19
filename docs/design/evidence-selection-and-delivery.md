# Evidence selection and delivery across briefing and consult packing

Status: briefing selection and consult packing implemented 2026-10-19. Issue: #258. Continues the shipped
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
This table shows coverage of lens labels, not better briefs. The semantic
effect on useful supported positions is untested; a later briefing review
should compare both policies under the same allowance and reject the balanced
policy if it preserves more labels but worsens supported answers.

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
answer; it needs the blinded review described in #258 and #259.

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
