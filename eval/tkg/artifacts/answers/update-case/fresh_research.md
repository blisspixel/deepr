Arm: fresh_research
Mode: offline_extract ($0, no model).
Evidence used: frozen source-world supporting sources.

Answer:
- [src-w2-reject-single-ts] The earlier informal claim that knowledge graphs need only one timestamp is wrong for bi-temporal workloads. Single-timestamp designs fail late-arriving correction and dual as-of queries.
- [src-w2-distractor-delete] The cleanest update is hard-delete of the prior edge so only the new truth remains.
- [src-w2-axes-hold] Valid-time and transaction-time remain distinct axes after system evolution. Foundations from the prior freeze still hold.
- [src-w2-invalidation] When a contradiction arrives, invalidate or supersede the current valid interpretation of an edge without deleting the transaction history needed for audit and as-of reconstruction.
