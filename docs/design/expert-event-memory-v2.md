# Expert Event Memory V2

Status: researched architecture proposal, 2026-07-10. No authority migration or
multi-device merge is shipped.

## Decision direction

Durable expert memory should become a versioned bitemporal event system, not a
set of mutable summaries with an auxiliary log. Existing beliefs, indexes,
self-models, memory cards, digests, and search structures should become
rebuildable projections only after shadow replay proves exact equivalence.

Current evidence:

- Graphiti models conversations, entities, relationships, and historical
  validity as a temporal knowledge graph
  ([paper, 2025-01](https://arxiv.org/abs/2501.13956)).
- Selective memory addition and deletion can outperform uncontrolled memory
  growth, which can propagate errors
  ([How Memory Management Impacts LLM Agents, 2025-05](https://arxiv.org/abs/2505.16067)).
- LongMemEval separates extraction, multi-session reasoning, temporal
  reasoning, updates, and abstention
  ([ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html)).
- LongMemEval-V2 extends this to dynamic state, workflows, environment gotchas,
  and premise awareness
  ([2026-05](https://arxiv.org/abs/2605.12493)).
- BeliefShift evaluates contradiction detection and evidence-driven revision
  rather than static recall
  ([2026-03](https://arxiv.org/abs/2603.23848)).
- Memora measures reliance on invalidated memories
  ([2026-04](https://arxiv.org/abs/2604.20006)).
- EvolveBench exposes temporal misalignment failures
  ([ACL 2025](https://aclanthology.org/2025.acl-long.788/)).
- CRDT practice supports globally distinct revisions, append-only histories,
  tombstones, offline merge, and deterministic storage convergence. It cannot
  resolve semantic belief conflicts
  ([Xi design](https://xi-editor.io/docs/crdt-details.html)).

## Proposed authority

A future `ExpertEventV2` should include event and schema ids, expert and
replica ids, actor, hybrid logical and wall time, causal parents, operation,
target type and id, before ref, after payload or ref, evidence refs, world-valid
time, observed and recorded time, supersedes and retracts refs, verification
state, grounding assurance, and idempotency key.

Canonical serialization and content hashing identify events. JSONL plus SQLite
materialized projections are sufficient initially. A graph database should
wait for measured query or scale requirements.

## Bitemporal graph

Maintain both world-valid time and record time. Node lanes include:

- factual claim and belief versions;
- entities, concepts, evidence, and sources;
- episodes, runs, actions, decisions, and failures;
- gaps, hypotheses, stances, and original ideas;
- self-model proposals and accepted identity records;
- policies and governance.

Edges include `supports`, `contradicts`, `supersedes`, `invalidates`,
`derived_from`, `observed_in`, `used_in`, `scoped_to`, `caused_by`,
and `resolves`. Revision creates a new version and explicit edge. It does not
erase or silently overwrite history.

Required queries are current truth, world state at time T, what Deepr believed
at record time R, why a claim changed, and which actions used a now-invalid
belief.

## Memory and identity lanes

Keep factual world model, perspective state, episodic experience, and
governance or identity distinct. Retrieval may compose lanes, but every item
retains its authority. An outcome may add episode evidence; it cannot directly
rewrite identity. Accepted identity changes require explicit reviewed events.

## Revision and forgetting

The mutation path remains:

`candidate -> semantic judgment -> evidence validation -> review when needed
-> graph commit -> append event -> deterministic projection`

Deterministic code owns schemas, ranges, budgets, temporal ordering, hashes,
and writes. Calibrated model or human judgment owns meaning, contradiction,
atomicity, and deduplication.

Forgetting has three distinct meanings:

- epistemic forgetting lowers retrieval priority or archives obsolete state;
- operational compaction rebuilds snapshots and indexes without losing events;
- privacy deletion follows a separate erasure policy with minimal
  non-reversible tombstone metadata where lawful and appropriate.

Before archival changes, simulate against frozen cases. Protect contested
beliefs, evidence roots, identity and policy records, high-trust claims, and
claims used by unresolved decisions.

## Multi-device merge

Every device receives a stable replica id. Sync unions validated events by
event id and deterministically rebuilds projections.

- Storage convergence can be automatic.
- Semantic convergence cannot.
- Concurrent claim revisions remain branches or contested state.
- Last-write-wins is limited to explicitly low-risk scalar preferences.
- Retractions and archives synchronize as tombstones.
- Unknown schemas or untrusted signers enter quarantine.
- Causal parents and logical time govern replay; wall time is advisory.

Multi-device work must not precede exact deterministic replay.

## Promotion evidence

Evaluate indexing, retrieval, and action separately. Track temporal accuracy,
contradiction resolution, supersession, provenance, replay exactness, replica
convergence, stale-memory leakage, abstention, held-out task success,
calibration, grounding, cost, latency, and perspective stability.

Before-and-after runs hold model, prompt, context allowance, and budget
constant. Promotion requires improvement without material regression in
calibration, grounding, stale-memory leakage, prior-correct cases, or identity
stability.

## Dependency order

1. Approve an ADR for event authority, time semantics, identity authority,
   deletion policy, and migration invariants.
2. Freeze Deepr-specific held-out baseline cases.
3. Add ExpertEventV2, replica identity, causal parents, hashes, and shadow
   replay.
4. Dual-write and prove replay equality before switching authority.
5. Build bitemporal projections and consolidate duplicate temporal state.
6. Make revision immutable with explicit supersession and contestation.
7. Enforce memory-lane authority in retrieval and graph commits.
8. Add simulated selective-forgetting proposals and protected classes.
9. Add event synchronization and replica convergence tests.
10. Enable held-out promotion gates.
