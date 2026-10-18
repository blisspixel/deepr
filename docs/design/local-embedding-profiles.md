# Local embedding roles and index compatibility

Date: 2026-10-18. Scope: issue #216.

The local embedder currently sends identical raw strings for document indexing
and queries. Its vector index binds only model label and claim bytes. Prefix or
dimension changes could therefore reuse incompatible vectors and route evidence.

## Decision

Add a small versioned input-profile seam with explicit query/document roles.
Profiles are `none`, `nomic-v1`, and `embeddinggemma-fact-checking-v1`; `auto`
selects the documented profile only for a recognized model family. Unknown
models remain raw. Existing defaults remain `none` until a sufficiently useful
comparison justifies promotion. Selection uses model identity, never an inferred
semantic classification of the text.

Nomic query/document prefixes follow its model card. EmbeddingGemma fact-checking
queries use the claim task prefix and documents use `title: none | text:`;
no title is invented from the belief text. Gemma supports native 768 dimensions
and explicit 512/256/128 truncation followed by L2 normalization. Queries and
indexed documents must have the same effective dimension. Empty, zero, nonfinite,
malformed or incorrectly ordered response vectors fail rather than producing
plausible scores. No new library is needed.

Persist the resolved versioned profile with each vector. Legacy records lacking
a profile mean `none`. Refresh treats a profile or requested dimension mismatch
as stale and changes only the derived vector index, never canonical beliefs.
Read paths filter by profile and query dimension, and state digests include the
profile/dimension contract so cached route qualifications cannot survive it.
A configured-profile mismatch cannot silently become a comparison of mixed data.

Expose matching options on refresh, semantic recall and recall evaluation.
Precomputed inputs can declare their profile, but this is operator provenance,
not a claim that Deepr produced or verified them. The raw maintenance and MCP
paths remain compatible only with raw vectors unless explicitly supplied a
matching contract. Recall remains candidate routing with no semantic verdict.

Local embedding invocations use the canonical durable attempt recorder, with an
embedding operation kind, current owned-local cloud/model proof and explicit
synthetic proof adapters in tests. Persistence failure blocks dispatch or
surfaces an unsettled result. Empty batches create no attempt. There is no
metered fallback, automatic model download or new network authority.

## Verification and promotion

Reproduce missing role prefixes, stale-profile reuse and dimension mixing.
Verify refused proof, persistence failures and malformed responses before
qualification. Freeze labeled recall cases and copied belief stores before a
local comparison of raw Nomic, prefixed Nomic, Gemma768 and Gemma256; retain
source/model identities, profile, dimensions, latency, vectors, ledger and
metrics. Labels are supplied evaluation data, never a keyword-derived verdict.
A synthetic labeled fixture establishes behavior on that fixture only. It does
not qualify expertise, advance S0 or automatically change a default.

Primary sources checked 2026-10-18:
- https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
- https://huggingface.co/google/embeddinggemma-2
- https://ollama.com/library/embeddinggemma-2:270m

Both model cards use Apache 2.0. The Ollama tag currently lists MLX and llama.cpp
artifacts; actual daemon support and the materialized digest must be observed.
No backend or precision is inferred from a download-size label.
