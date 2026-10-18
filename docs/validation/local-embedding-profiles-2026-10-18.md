# Local embedding profile comparison, 2026-10-18

Issue #216. See [design](../design/local-embedding-profiles.md) and the
[generated comparison record](embedding-profile-comparison-2026-10-18.json).

The baseline regressions exposed identical query/document inputs, profile
changes treated as current vectors and dimension mismatches accepted by index
lookup. The repair adds explicit role profiles, stored profile identity,
profile/dimension staleness and durable native embedding attempt accounting.
Legacy vectors mean `none`. Raw input remains the default. Unknown model
families stay raw under `auto`; mismatched explicit profiles fail before client
construction. Gemma truncation requires native 768-dimensional output, supported
sizes and a finite nonzero L2 norm. Failed responses cannot yield a score.

The local comparison used the published [BEIR SciFact test labels](https://github.com/beir-cellar/beir#available-datasets),
from [SciFact](https://github.com/allenai/scifact), rather than generated relevance
judgments. Before embedding, 40 query IDs were selected by a recorded SHA256
ranking; all 44 positive documents plus 128 deterministically selected other
abstracts formed a 172-document fixture. The original archive, published checksum,
SHA256 hashes, complete source bytes, labels and selection policy are retained.
This is a subset comparison, not the full SciFact benchmark.

| Local configuration | Hit@5 | MRR@5 | Recall@5 | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| Nomic v1.5, raw | 0.9500 | 0.9313 | 0.9500 | 0.9358 |
| Nomic v1.5, query/document prefixes | 0.9500 | 0.9008 | 0.9500 | 0.9106 |
| EmbeddingGemma 2, fact-checking, 768d | 1.0000 | 0.9675 | 1.0000 | 0.9746 |
| EmbeddingGemma 2, fact-checking, 256d | 1.0000 | 0.9800 | 1.0000 | 0.9847 |

Nomic prefixes did not improve this fixture. Gemma's result on this small subset
does not justify a general replacement recommendation. Defaults remain raw;
profile use and re-embedding are explicit. Sparse qrels can omit useful documents.
Fixed order and warm models make recorded timings descriptive only.

Ollama 0.40.6 reported cloud disabled by configuration. Both models materialized
as local GGUFs: Nomic v1.5 digest `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`
and Gemma 270m Q8_0 llama.cpp digest
`c21dd30c1e38444d3b4faa091407b6fa97221447b4965d74931d43d7f09bbbfd`.
The actual Gemma responses were 768-dimensional. Internal inventory fields
reported a 512-wide backbone and a larger architectural context; these do not
replace the model card's 768-dimensional output and 8K text-input contract.

The final run used the frozen project environment, eight inputs per batch and
the production local embedder, refresh helper and recall evaluator. Every
prepared query/document input and returned vector is retained with its model,
role, profile, timestamps and source snapshot. Exactly 108 attempt identities
reconcile to 324 requested/dispatch/terminal ledger events at `$0.00`. Canonical
fixture belief files retain their original hashes. No paid provider was called.
The original global-Python diagnostic and the earlier locked run remain separate;
the final run adds complete query-vector retention for offline replay.

Offline checks cover malformed vectors/indices, model/profile mismatch, proof
and ledger refusal, dimension mixing, immutable canonical beliefs, CLI option
parity, schema validation and changed routing qualifications. An old exact-shape
fixture needed the new profile fields. A new CLI test initially ran inside an
async test loop; it was corrected to use the synchronous CLI harness. Those
failed trials remain retained, with no assertion or gate weakened.

Full-suite, installed-wheel and publication results accompany the matching PR
and release. No codegraph was available; source callers and tests were traced.
All local evidence is under the existing ignored `.agent/reader-evidence/`.
Retrieval metrics do not certify advice, expertise, currentness or S0.
