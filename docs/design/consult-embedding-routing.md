# Optional local embedding routing for consult findings

Status: implemented 2026-10-19, off by default. Issue: #264. Measured with
the [correction survival diagnostic](correction-survival-diagnostic.md).

## Problem

Consult offers study findings by literal token overlap, up to 24, after the
findings that selected positions cite. With 60 on-topic distractor sources the
diagnostic's `near-match-version` case lost its v2 finding at retrieval: filler
mentioning "agents" and "default" outscored a finding that says "agent
platform", and no position cited the finding. Plural folding alone does not
fix it, because the filler still shares more words with the question.

## Decision

An opt-in router fuses the lexical order with local embedding similarity:

- `consult.embedding_model` (`DEEPR_CONSULT_EMBEDDING_MODEL`) names an
  installed local Ollama embedding model. Unset, consult is unchanged.
- `experts/consult_routing.py` embeds the question (query role) and the
  expert's study findings (document role) through `make_local_embedder` with
  the model's known profile, so every call is owned local capacity with
  durable `$0` receipts and an attested digest.
- `build_consult_context` takes the resulting order as `semantic_ranking` and
  fuses it with the lexical order by reciprocal rank (k = 60, at most 24
  semantic candidates). Position-cited support is still carried first.
- The packet's limitations say routing used embedding similarity and that
  similarity chose candidates without establishing relevance. The perspective
  context records `finding_routing`. Any routing failure falls back to
  lexical routing with a note naming the error type.
- One setting covers CLI and MCP, because both reach `run_consult`.
- `deepr eval correction-survival --embedding-model MODEL` routes the
  diagnostic's production arm the same way.

## Measurement

Production path with mock answers, 18 source-backed obligations:

| Distractors | Lexical | `nomic-embed-text:v1.5` | `embeddinggemma-2:270m` |
|---|---|---|---|
| 0 | 18 of 18 delivered | 18 of 18 | 18 of 18 |
| 60 | 17 (1 missed at retrieval) | 18 of 18 | 18 of 18 |
| 150 | 17 (1 missed at retrieval) | 18 of 18 | 17 (selected, then omitted by the prompt limit) |

At 150 distractors embeddinggemma retrieved the finding but the packer
dropped it at the prompt bound, a different stage that the receipts separate.
Routing changes which findings compete for the prompt; it does not enlarge it.

Ranking findings alone at 60 distractors, without position-carried support
(`.agent/correction-survival-2026-10-19/routing_experiment.py`), put 6 of 16
obligation findings in the top 24 lexically, 8 with nomic, 12 with
embeddinggemma. Most production retrieval therefore still rests on positions
citing their support; the router helps the findings no position carries.

## Alternatives rejected

- **Stemming or plural folding.** Does not change the ranking here.
- **BM25 weighting.** The filler shares every matched term with the finding,
  so term weighting cannot separate them.
- **Raising the 24-finding cap.** Moves the cliff and spends prompt room on
  filler.
- **Default-on routing.** Adds a local model call to every consult and
  depends on an installed embedding model. It stays opt-in until a reviewed
  semantic comparison shows answers improve, not just delivery counts.

## Limits

Synthetic worlds with designed filler. Delivery counts are not answer quality.
Finding vectors are recomputed per consult; an index can follow if latency
matters. No promotion to default without reviewed answers.

## Identity and diagnostic accounting repair (2026-10-20, #259)

Decision recorded before implementation: bind a router's query and document calls, including
later attempts using that router, to the first attested model digest, resolved
input profile and vector dimensions. Recheck owned-local proof before every
dispatch. A changed identity refuses the ranking and uses the existing disclosed
lexical fallback. Do not compare equal-sized vectors from different revisions.
Standalone embedding callers keep the existing vector-returning callable seam;
optional shared identity and receipt collection reuse the local backend.

The diagnostic records configured and effective routes separately per attempt,
success/fallback/unused status, error reason, pinned identity and references to
the canonical native-local attempt ledger. Collect content-free summaries of
returned, failed, refused and unsettled calls, with unknown token usage explicit.
These summaries reference the existing ledger; they are not a second ledger.

Keep legacy `elapsed_ms` as answer-only latency and name it explicitly. Add
routing and total-attempt elapsed time measured before routing through answer
completion, including packet assembly. Report per-arm totals and effective-route
counts; legacy runs have unknown routing/total timing rather than invented
zeros. Source/study/brief fixture materialization is shared setup outside the
attempt, not end-to-end research time. Preserve full prompt/answer hash binding
and completion-marker checks; include embedding identity/profile/backend code
in the recipe identity. No migration or rewriting of retained runs.

Use mocked local attestation/transport and a controlled clock to test tag
changes between query/documents and between attempts, dimension mismatch,
failure after dispatch, missing usage, and actual elapsed time. No new inference
or semantic review is needed for this repair; existing answers stay unreviewed.
The lexical default, capacity/spend boundaries and canonical expert writes do
not change. This guards identity and side effects, not meaning.

Rejected: a second ledger, trusting a mutable tag or matching vector lengths,
silently relabeling legacy answer latency as total time, or default promotion
based on mechanical delivery counts.

The [dated verification](../validation/consult-routing-accounting-2026-10-20.md)
records the failing baseline, controlled-clock comparison, full offline suite
and source CLI check. Blinded semantic review remains open.
