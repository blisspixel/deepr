# Belief store write transactions

Status: implemented 2026-10-18. Roadmap: "Replace verb-specific write guards
with one per-expert knowledge-mutation transaction".

## Problem

`BeliefStore` loads the whole `beliefs.json` snapshot when constructed and
rewrites the whole snapshot on every mutation. Verb locks (`absorb`, `sync`,
`graph-commit-apply`, `investigation-learning-apply`, and others) are keyed by
(expert, verb), so two *different* verbs can run at once. A sync that loaded
the store before an absorb committed later rewrites the snapshot from its
stale copy: the absorb's beliefs vanish from the snapshot while their events
stay in the append-only `events.jsonl`. When the surviving snapshot's latest
change is older than the log's latest event, the next load marks the store
unreadable and refuses writes. The 2026-07-11 same-verb guard closed only the
absorb/absorb case.

## Decision

The store owns the transaction, because it is the canonical belief authority
(`AGENTS.md` seams) and every interface writes through it:

- Each mutator runs inside `BeliefStore.mutation()`, a reentrant context that
  holds a per-store cross-process file lock (`beliefs/beliefs.lock`, blocking
  with a bounded wait). Mutations are short in-memory edits plus one snapshot
  write; no model call happens under the lock.
- On entry the store compares the on-disk fingerprint (snapshot stat and event
  log size) with the one it last read or wrote. If another process committed
  in between, it reloads before applying the mutation, so dedup and conflict
  checks see current state.
- If the store holds unsaved in-memory edits (`add_edge(save=False)` batches)
  and the disk changed, it raises `BeliefStoreConflictError` instead of
  reloading over them.
- Plain loads take no lock and create no file: snapshots are replaced by
  atomic rename, and read-only launches must leave expert data byte-identical
  (the agent-plugin smoke checks this).
- `_save()` refuses to overwrite a snapshot that changed since it was last
  seen, so an unwrapped direct mutation fails closed instead of silently
  overwriting. Multi-step external writers (`graph_commit_apply`,
  `world_validity.affirm_in_force`) wrap their read-check-write sequence in one
  `mutation()`.

Verb locks stay: they still prevent duplicate same-verb work and spend before
model construction. They are no longer the only protection for belief data.

## Alternatives rejected

- **One per-expert lock held for a whole verb.** Correct but serializes
  multi-minute local generations: a scheduled sync would block or skip every
  absorb. The data race is in the commit, not the generation.
- **Merging stale snapshots at save time.** Generic three-way merge of
  updates, archives and edges encodes conflict semantics the store does not
  own; reload-then-apply keeps the existing conflict rules authoritative.
- **Rebuilding the snapshot from the event log.** The event log is not yet
  complete enough to replay every field (usage counters are state, not
  events), so it cannot be the write path today.

A real graph-commit apply runs its validation and writes in one transaction,
so idempotency checks see any concurrent commit. When a mutation raises, the
store reloads the last commit instead of keeping half-applied edits; if that
reload fails, the instance refuses further writes. A legacy migration save that
meets a concurrent write during load is deferred to the next transaction.

## Limits

An in-process reader on another thread can briefly observe the store mid-reload,
because reads take no lock. Fingerprints use stat (mtime, size, inode), which is
weaker on filesystems without inode numbers or with coarse timestamps.

Profile counters and per-verb sidecars (subscriptions, loop runs) keep their
own write paths. Candidates a verb computed from a stale view are still
re-checked at commit by the store's existing dedup, which is lexical routing,
not a semantic verdict.
