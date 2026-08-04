Arm: maintained_expert
Mode: offline_extract ($0, no model).
Evidence used: frozen source-world supporting sources and stored expert packet.

Answer:
- [src-w2-reject-single-ts] The earlier informal claim that knowledge graphs need only one timestamp is wrong for bi-temporal workloads. Single-timestamp designs fail late-arriving correction and dual as-of queries.
- [src-w2-distractor-delete] The cleanest update is hard-delete of the prior edge so only the new truth remains.
- [src-w2-axes-hold] Valid-time and transaction-time remain distinct axes after system evolution. Foundations from the prior freeze still hold.
- [src-w2-invalidation] When a contradiction arrives, invalidate or supersede the current valid interpretation of an edge without deleting the transaction history needed for audit and as-of reconstruction.
- Stored expert context excerpt: Stored belief perspective for Temporal Knowledge Graphs. Selected stored beliefs by query-token overlap, then confidence. 8 of 100 active beliefs included. - (0.60, temporal and bi-temporal knowledge graphs: valid-time vs transaction-time, point-in-time queries, edge invalidation on contradiction, confidence trajectories, Graphiti/Zep approaches) As-of observed time queries retrieve what the agent believed as of a specific time. Sources: report:file:report.md - (0.60, temporal and bi-temporal kn
- Maintained posture: prefer current beliefs; treat invalidated history as non-current.
