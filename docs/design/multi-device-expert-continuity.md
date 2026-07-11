# Multi-Device Expert Continuity

Status: staged design, 2026-07-10. Current shipped mode is sequential-device
portability only.

## Problem

`deepr init --data-dir PATH` configures `DEEPR_DATA_DIR`,
`DEEPR_EXPERTS_PATH`, and `DEEPR_REPORTS_PATH` below one chosen root. Setting
`DEEPR_DATA_DIR` alone relocates experts and operational runtime state, while
reports continue to use their separate configured root. A user can put the
coordinated root in OneDrive, Dropbox, iCloud Drive, or Syncthing and move
between devices. That is useful, but generic file sync is not a database
replication protocol.

The previous documentation said experts simply "follow you across machines."
That omitted the load-bearing constraint: two devices must not mutate the same
expert concurrently, and the user must wait for synchronization to finish
before switching writers.

## Current evidence

- SQLite warns that remote filesystem locking and synchronization vary by
  implementation and can cause corruption when multiple systems write through
  an unreliable locking layer
  ([SQLite, accessed 2026-07-10](https://www.sqlite.org/useovernet.html),
  [corruption guidance](https://www.sqlite.org/howtocorrupt.html)).
- Dropbox creates a conflicted copy when multiple devices edit the same file or
  edit offline concurrently. It does not semantically merge arbitrary
  application state
  ([Dropbox Help, accessed 2026-07-10](https://help.dropbox.com/organize/conflicted-copy)).
- Syncthing similarly preserves a clashing file instead of pretending it can
  merge incompatible contents
  ([Syncthing documentation, accessed 2026-07-10](https://docs.syncthing.net/users/syncing)).

Deepr's append-only ledgers, JSON state, derived views, and local databases have
different merge semantics. Treating them all as ordinary files hides conflicts
instead of resolving them.

## Shipped contract

Current v2.34.4 behavior is intentionally conservative:

- experts and reports may be placed in a synced folder for sequential use;
- only one device may run mutating Deepr commands at a time;
- the user must let the sync provider finish before changing devices;
- `DEEPR_DATA_DIR` also roots queues, traces, benchmark caches, observability
  artifacts, and several MCP operational databases, so those files share the
  same sequential-only constraint when the whole root is synced;
- cost and capacity ledgers can use their dedicated root overrides to remain
  machine-specific;
- `deepr doctor` states the one-writer constraint instead of advertising
  unrestricted sharing.

Local `filelock` guards protect processes on one device. They do not coordinate
two offline devices and must not be marketed as cross-device exclusion.

## Target architecture

The long-term design should make canonical expert mutations mergeable without
requiring an always-on Deepr service.

### Device identity

Each installation receives a stable random device id and a human label. Device
identity is metadata, not authority. Secrets and provider credentials remain
local. Cost state and machine capability should remain local through dedicated
roots rather than depending on the shared `DEEPR_DATA_DIR` default.

### Device-partitioned event journals

Canonical mutations are written to immutable per-device journals rather than a
shared file:

`experts/<slug>/events/<device-id>/<event-id>.json`

An event contains a globally unique id, device id, causal parent refs, observed
time, effective time, schema version, provenance, mutation kind, and content
hash. A device never appends to another device's journal, so file-sync conflict
copies cannot split one logical append operation.

### Deterministic merge

A `$0` merge command folds all valid journal events into a derived snapshot.
It is idempotent by event id and content hash. Independent additions commute.
Concurrent revisions of the same belief, stance, or policy remain explicit
branches until a human or calibrated verifier adjudicates meaning. Deletes use
tombstone events and never silently erase unseen peer state.

The merge layer owns form, causality, idempotency, schemas, and conflict
surfacing. It does not decide semantic equivalence, contradiction, or which
perspective is correct.

### Sync health

A read-only `deepr device status` surface should report:

- local device id and label;
- last observed event per peer;
- unmerged event count;
- divergent branches and tombstones;
- detected provider conflict-copy files;
- missing or invalid event hashes;
- whether a device is safe to switch into write mode.

It should never infer safety from a cloud provider's green icon alone.

## Migration sequence

1. **Shipped now:** correct docs and doctor guidance to sequential-only use.
2. Add device identity plus read-only sync-health and conflict-copy detection.
3. Introduce additive per-device journals for new belief and perspective
   mutations while continuing to render current snapshots.
4. Build deterministic import and merge with explicit conflict artifacts.
5. Migrate remaining canonical expert stores one kind at a time.
6. Consider an optional encrypted relay only after local folder replication is
   proven. A relay is not required for the event model.

## Non-goals for concurrent continuity

- The future concurrent architecture must not merge the append-only cost
  ledger, active queue, traces, credentials, or device capability observations.
  Coordinated setup places some runtime artifacts below the current
  sequential-only root; separating them is a prerequisite for concurrency.
- Do not open one SQLite database from multiple devices through a shared
  filesystem.
- Do not claim local file locks coordinate offline devices.
- Do not resolve semantic conflicts by last-write-wins.
- Do not introduce a central service as a prerequisite for local use.

## Acceptance criteria for concurrent multi-device claims

Deepr may claim concurrent multi-device expert editing only after tests prove:

- two offline devices can add independent events and merge without loss;
- same-entity concurrent edits remain visible and recoverable;
- replay is deterministic across Windows, macOS, and Linux;
- event duplication and reordering are idempotent;
- malicious or corrupt peer events fail closed by schema and hash;
- invalidated memory and tombstones survive merge;
- derived snapshots can be deleted and regenerated from journals.
