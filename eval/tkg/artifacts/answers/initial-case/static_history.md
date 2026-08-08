Arm: static_history
Mode: offline_extract ($0, no model).
Evidence used: frozen source-world supporting sources.

Answer:
- [src-w1-valid-tx] A bi-temporal knowledge edge records valid-time (when the fact is true in the world) separately from transaction-time (when the system learned or recorded it). Collapsing both into one timestamp loses either real-world history or system audit history.
- [src-w1-single-ts-risk] A store that keeps only one timestamp cannot both answer 'what was true on date D' and 'when did we learn that' after late-arriving corrections.
- [src-w1-as-of] Point-in-time (as-of) queries must answer against a chosen time axis. An as-of valid-time query asks what was true then; an as-of transaction-time query asks what the system believed then.
