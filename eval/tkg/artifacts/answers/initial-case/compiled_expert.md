Arm: compiled_expert
Mode: offline_extract ($0, no model).
Evidence used: frozen source-world supporting sources and stored expert packet.

Answer:
- [src-w1-valid-tx] A bi-temporal knowledge edge records valid-time (when the fact is true in the world) separately from transaction-time (when the system learned or recorded it). Collapsing both into one timestamp loses either real-world history or system audit history.
- [src-w1-single-ts-risk] A store that keeps only one timestamp cannot both answer 'what was true on date D' and 'when did we learn that' after late-arriving corrections.
- [src-w1-as-of] Point-in-time (as-of) queries must answer against a chosen time axis. An as-of valid-time query asks what was true then; an as-of transaction-time query asks what the system believed then.
- Stored expert context excerpt: Stored belief perspective for Temporal Knowledge Graphs. Selected stored beliefs by query-token overlap, then confidence. 8 of 100 active beliefs included. - (0.60, temporal and bi-temporal knowledge graphs: valid-time vs transaction-time, point-in-time queries, edge invalidation on contradiction, confidence trajectories, Graphiti/Zep approaches) As-of observed time queries retrieve what the agent believed as of a specific time. Sources: report:file:report.md - (0.60, temporal and bi-temporal kn
