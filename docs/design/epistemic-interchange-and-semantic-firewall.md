# Epistemic interchange and semantic firewall

Status: planned design, with a `$0` write-free experiment defined below. No
new import, ontology, or mutation surface is shipped by this document.

## Outcome

Deepr should make an important judgment traversable in both directions:

```text
position
  -> supporting belief
  -> source assertion
  -> exact evidence anchor
```

```text
new evidence
  -> staged source assertion
  -> local semantic decision
  -> belief revision
  -> changed position
```

This is the concrete query that justifies more explicit epistemic types. It is
not a reason to replace the current stores, add RDF infrastructure, or make a
graph visualization a product goal.

The design has two jobs:

1. preserve exact evidence and source independence across tool boundaries;
2. let deterministic code reject impossible state transitions without
   pretending it can judge meaning.

## Product boundary

The sibling projects remain standalone products with independent release
lifecycles and canonical stores:

```text
Distillr: evidence memory
  sources -> atomic evidence -> concepts -> corpus knowledge

Deepr: judgment memory
  evidence -> beliefs -> positions -> hypotheses -> revisable judgment

Primr: case analysis
  company evidence -> strategic findings -> inferences -> decision artifact
```

This is a conceptual contract, not a Python dependency graph. Interchange uses
versioned artifacts or MCP. A sibling never writes Deepr's belief, edge,
position, event, or authority stores directly.

OKF 0.2 remains the portable, human-readable projection for selected
knowledge. It is not detailed enough to be the canonical machine handoff for
exact evidence spans and local admission decisions. A separate versioned
JSON/JSONL finding envelope may carry those details while remaining an
untrusted ingestion artifact.

The governing rule is:

> Interchange contract is not canonical store.

## Epistemic vocabulary

The cross-project vocabulary describes kinds, not a ladder of increasing
truth:

| Kind | Meaning | Deepr admission posture |
|---|---|---|
| Observation | Directly captured material or measurement | Preserve as evidence; do not infer truth from capture alone |
| Source assertion | A source asserts a proposition | Stage immutably with exact provenance |
| Belief | Deepr's current, revisable factual judgment | Admit only through Deepr verification and apply authority |
| Inference | A stated conclusion from identified premises | Preserve as a proposal until its support is adjudicated |
| Hypothesis | A possibility with expected observations and disconfirmers | Keep separate from factual belief authority |
| Position | Deepr's current judgment on a question | Derived from admitted state and versioned independently |

A decision is an outcome that may consume these kinds. It is not another truth
class.

An upstream artifact that labels a record `belief` does not become a Deepr
belief. It enters as a source assertion about what that producer states, or it
stays quarantined for review. Upstream confidence, verification, trust,
independence, and relation labels are advisory provenance only.

## Identity model

Three identities must remain separate:

1. `source_id` identifies the source origin used for independence accounting;
2. `source_assertion_id` identifies one assertion instance from that source;
3. `anchor_id` identifies one exact evidence selection.

Multiple anchors from one source do not create multiple independent sources.
Multiple sources may make equivalent assertions without becoming one
assertion. A later proposition identity can group semantically equivalent
assertions after model or human adjudication. Exact hashes may identify bytes
and records, but they do not decide semantic equivalence.

This separation fixes an important failure mode: `same_as_existing` should
avoid a duplicate belief without discarding a new, independently sourced
assertion that corroborates it.

## EvidenceAnchor v1

An evidence anchor is a vendor-neutral locator value. It is not a semantic node
and cannot directly ground a belief. The required bridge is:

```text
EvidenceAnchor
  <- anchored source assertion
  - grounds after local semantic adjudication
Belief
```

The initial normalized text-span form should carry:

```json
{
  "schema_version": "deepr-evidence-anchor-v1",
  "anchor_id": "sha256:...",
  "source_id": "...",
  "artifact_ref": "...",
  "artifact_sha256": "...",
  "representation": "normalized_text_v1",
  "representation_sha256": "...",
  "locator": {
    "type": "text_span",
    "start_codepoint": 1432,
    "end_codepoint": 1719
  },
  "selected_text_sha256": "...",
  "selected_text": "optional bounded excerpt"
}
```

Text spans are half-open Unicode code-point offsets into one named normalized
representation. The artifact and representation digests distinguish the
original bytes from the text used for span validation. Optional native
navigation locators can be additive:

- PDF page and bounding box;
- transcript start and end seconds;
- HTML heading path;
- repository commit, path, and line range.

Native locators improve navigation. The normalized representation and digests
own replay and stale-anchor detection. Locators never carry credentials or
unbounded source content.

Deterministic validation can prove schema shape, digest form, span bounds,
ordering, exact containment, and artifact identity. Whether the selected span
expresses the source assertion is semantic judgment. Whether that assertion
grounds the target belief is also semantic judgment.

## Time semantics

Every admitted record needs a total system-history axis:

- `recorded_at`: when Deepr recorded the event;
- `superseded_at`: when that recorded version stopped being current.

Source-dependent time is optional and must stay sparse:

- `observed_at`: when the source says an observation occurred;
- `valid_from` and `valid_until`: the interval the assertion is judged to
  describe;
- `retrieved_at`: when Deepr or an upstream producer retrieved the artifact.

Missing source time remains unknown. Deepr must not invent a validity interval
from publication time, retrieval time, or file modification time. The planned
ExpertEventV2 authority still owns any eventual canonical bitemporal replay.

## Atomic finding envelope

The machine handoff should be append-only and candidate-only. A minimal record
contains:

```json
{
  "schema_version": "deepr-atomic-finding-v1",
  "producer": {"name": "...", "version": "...", "run_id": "..."},
  "producer_artifact_sha256": "...",
  "source": {"source_id": "...", "independence_group": "..."},
  "assertion": {
    "source_assertion_id": "...",
    "statement": "...",
    "epistemic_kind": "source_assertion",
    "anchor_ids": ["sha256:..."]
  },
  "proposed_relations": [],
  "authority": "candidate_only"
}
```

The complete contract will also bound strings and collections, define
canonical serialization, preserve source trust and retrieval metadata, and
bind each proposed relation to its own producer relation identity. Those are
format decisions, not semantic acceptance.

## Admission pipeline

Direct atomic handoff means avoiding redundant re-extraction from prose. It
does not mean bypassing Deepr's maker-checker and explicit apply boundary.

```text
external finding packet
  -> parse and root-confine
  -> verify envelope and artifact digests
  -> validate anchors and exact containment
  -> register immutable candidate source assertions
  -> recall possible existing beliefs
  -> local semantic verification
  -> build a write-free commit envelope
  -> explicit, idempotent apply
```

The import receipt binds producer identity, producer artifact digest, local
artifact identity, and parser version. It grants no spend, tools, network,
credential, storage, verification, or mutation authority.

An incomplete inference remains a quarantined inference proposal. It is never
silently converted into a factual belief. Proposed upstream relationships must
be re-adjudicated locally before a canonical Deepr edge can exist.

## The semantic firewall

The model or accountable human proposes semantic nodes and relations. A pure
compiler checks whether the proposal is structurally possible and whether the
required local decision receipt exists.

Do not collapse this into one `legal` boolean. Use separate axes:

```text
structural_status:
  valid | invalid

semantic_status:
  not_applicable | required | accepted | rejected | uncertain

stage_disposition:
  rejected | semantic_adjudication_required | admissible_for_stage
```

`admissible_for_stage` never means Python proved a relation true. Mutation
readiness is still the conjunction of structure, semantic assurance,
provenance, time, authority, admission, and idempotency.

### Shadow compiler v1

The first experiment is deliberately narrower than the eventual ontology. It
recognizes only authoritative records Deepr can already relate safely:

```yaml
node_types:
  source_assertion: {}
  belief: {}

relations:
  grounds:
    from: source_assertion
    to: belief
    requires_assurance: local_model_or_human_confirmed

  supports:
    from: belief
    to: belief
    requires_assurance: local_model_or_human_confirmed

  contradicts:
    from: belief
    to: belief
    symmetric: true
    requires_assurance: model_confirmed_with_current_protocol

  derived_from:
    from: belief
    to: belief
    acyclic: true
    requires_assurance: local_model_or_human_confirmed
```

`supports` uses evidence-to-conclusion direction. That direction must be frozen
in an ADR before any new canonical edge version ships because current read
paths are not fully consistent about it.

The existing `enables` edge remains a legacy belief relation until its desired
typed meaning is defined. `supersedes` remains version-ledger lineage in the
first experiment. Hypotheses and arguments remain in their existing stores or
proposal artifacts. They must not be disguised as beliefs merely to fit this
matrix.

### Deterministic ownership

Python owns:

- closed kind and relation enums;
- the permitted source-kind, target-kind, and direction matrix;
- authoritative endpoint existence;
- no self-edges;
- canonical symmetric identity for contradiction;
- duplicate relation identity;
- bounds, digests, timestamps, and source immutability;
- acyclicity where the declared relation requires it;
- decision-receipt presence, freshness, and exact proposal binding;
- candidate-only import authority, explicit apply, idempotency, and audit
  state.

Python does not own:

- whether an anchor entails a source assertion;
- proposition equivalence or semantic deduplication;
- whether one belief supports, contradicts, qualifies, or derives another;
- temporal scope compatibility;
- whether premises justify a conclusion.

A lexical or embedding score may nominate candidates. It cannot satisfy a
semantic assurance requirement.

Each accepted semantic edge needs an immutable local decision receipt binding
the proposal hash, typed endpoints, relevant assertion and anchor digests,
verdict, bounded rationale, verifier identity, verifier contract version,
timestamp, and import receipt. An upstream verification label cannot be copied
into that field.

## First measurable experiment

The first user-visible question is narrow:

> Can Deepr preserve independent corroborating evidence for an existing belief
> without creating a duplicate belief or admitting false support?

Run a `$0`, no-write shadow compiler over fixed, reviewed artifacts that include:

- one new source assertion that genuinely corroborates an existing belief;
- same-source repetition that must not increase independent-origin counts;
- a scope-qualified assertion that must not be treated as direct support;
- a contradiction candidate requiring the current fresh-context protocol;
- an unanchored and a stale-anchor negative;
- an upstream `verified` relation that Deepr must still treat as candidate-only.

Compare the current `same_as_existing` disposition with the proposed
`register_source_assertion` plus `grounds` proposal. Measure:

- corroborating assertion retention;
- duplicate-belief avoidance;
- exact position-to-source traversal coverage;
- false support and false contradiction rates;
- abstention and uncertain rates;
- order sensitivity;
- reviewer correction time;
- source independence accounting.

The compiler must run offline from recorded artifacts and make no paid calls.
Any local semantic judge remains an explicit eval input, never an automatic
mutation authority.

Promotion requires reviewed fixtures, relation-specific precision and recall,
bounded false-support performance, stable order-sensitivity results, and a
demonstrated reduction in lost corroboration or reviewer effort. Graph size and
number of compiled records are not success measures.

## Delivery sequence

This work follows the current four-arm expert-value review and immutable
falsifier prediction work in the roadmap.

1. Freeze kind meanings, relation direction, authority lanes, and transition
   rules in an ADR.
2. Implement a pure, write-free ontology classifier with exhaustive matrix and
   invariant tests.
3. Add immutable EvidenceAnchor and source-assertion staging.
4. Run the no-write corroboration experiment and publish its reviewed report.
5. Add local grounding decisions only if the experiment passes.
6. Add an additive graph-commit envelope version with typed endpoints and
   per-relation receipts. Preserve the current version unchanged.
7. Add explicit apply operations only after replay, idempotency, negative, and
   migration tests pass.
8. Extend the ontology to hypotheses or arguments only when a concrete read or
   mutation query and held-out eval justify each type.

## Rejected alternatives

- **Make prose canonical memory.** Rejected because summaries lose assertion
  identity, exact evidence, and derivation lineage.
- **Import an upstream verified belief directly.** Rejected because producer
  confidence is not Deepr verification or write authority.
- **Extend the existing belief edge enum in place.** Rejected because the
  current graph assumes belief endpoints and older artifacts need stable
  semantics.
- **Store source assertions, hypotheses, or arguments as fake beliefs.**
  Rejected because it erases authority boundaries.
- **Let an EvidenceAnchor directly ground a belief.** Rejected because text is
  not an assertion and containment is not entailment.
- **Use one legal or illegal result.** Rejected because structural validity and
  semantic assurance are different facts.
- **Adopt RDF or a graph database first.** Rejected because storage machinery
  does not define meaning and would widen migration risk before value is
  measured.
- **Add every planned node and relation at once.** Rejected because the first
  experiment needs only source assertions, beliefs, and exact provenance.

## Non-goals

- no cross-repository Python dependency;
- no direct sibling writes;
- no automatic paid dispatch;
- no private chain-of-thought storage;
- no graph visualization milestone;
- no transitive confidence inflation;
- no source-count inflation from repeated downstream coverage;
- no claim that a structurally valid graph is true or useful.
