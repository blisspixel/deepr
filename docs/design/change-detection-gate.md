# Pre-sync change-detection gate

Status: design note, updated 2026-07-01. Implements the source-pack content hash
and HTTP conditional request slices of the Phase 4d "pre-sync change-detection
gate" roadmap item. Cross-references [capacity-waterfall.md](capacity-waterfall.md)
(the $0-first routing this serves) and
[../plans/AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) (why this is a
workflow gate, not a meaning verdict).

## Problem

`deepr expert sync` researches each due subscription and then absorbs the answer
into beliefs through the verification-gated pipeline. Absorption runs a paid
extraction model call. In practice a large fraction of refresh runs find nothing
new: the same release page, the same docs, the same sources as last time. Today
two gates already skip that paid absorb - `_fresh_context_has_no_sources` (the
retrieval found nothing) and the model-side `no significant changes` reply. Both
sit after retrieval. Neither catches the most common case cheaply: retrieval
succeeded and returned the byte-identical sources it returned last sync, so
there is provably nothing new to absorb.

## The Signal

A content hash of each fetched source's extracted main content. ETags and
`Last-Modified` are advisory and server-dependent; a content hash is universal
and authoritative because a page re-saved with identical bytes keeps the same
hash even when its timestamp moves. Deepr hashes the extracted main content, not
raw HTML and not the search snippet, because that is the text the absorber
actually reads.

`FreshSource.content_hash` is a derived property (`sha256` of the stripped
content) unless an HTTP `304 Not Modified` response reuses a prior source-pack
hash. The hash, `etag`, `last_modified`, and `not_modified` fields are persisted
per source in both `FreshContext.to_source_pack()` and `to_metadata()`, which
means every sync writes the validators the next sync needs. No new datastore is
introduced; Deepr reuses the existing `sync_artifacts/source_packs/*.json`
artifacts.

External HTTP guidance checked on 2026-07-01:

- [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) says clients with
  entity tags should send `If-None-Match` on GET so servers can return
  `304 Not Modified`, and that `304` means the cached representation remains
  valid without transferring the representation body.
- MDN documents that
  [`If-None-Match`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-None-Match)
  takes precedence over `If-Modified-Since` when both are sent and the server
  supports ETags, while
  [`If-Modified-Since`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-Modified-Since)
  is the common fallback for cached resources without an ETag.

## The Gate

`fresh_sources_unchanged(prior, current)` in `experts/sync.py` is a pure,
deterministic function over the two source-pack dicts. It returns `True` only
when every content hash in the current retrieval already appeared in the prior
sync's pack. Current hashes are a subset of prior hashes, so the run added no
new content. `_sync_subscription` loads the most recent prior pack for the topic
before writing the current one, passes it to prior-aware local and plan-quota
context builders, and when the gate fires it records a `no_changes` outcome and
skips the paid absorb, exactly like the existing gates.

When a prior source has `etag` or `last_modified`, the built-in browser backend
sends `If-None-Match` and `If-Modified-Since` on the next HTTP fetch. A `304`
response reuses the cached excerpt for prompt context and the cached content
hash for the source-pack no-change proof; it does not invent a new hash from the
short excerpt. If the server returns `200`, the new body, ETag, Last-Modified,
and hash are recorded normally.

## Fail-Safe Direction

The gate fails safe toward proceeding, never toward skipping. It returns
`False` whenever it cannot prove no-change:

- no prior pack exists (first sync, or a new topic),
- the current run produced no hashable content (fetch failures, snippet-only
  sources),
- any current hash is absent from the prior pack (new or changed source),
- a prior artifact is unreadable, or sources predate this feature and carry no
  `content_hash`,
- a server returns `304` but Deepr has no prior source metadata to pair it with.

So a real update is never silently dropped. The only cost of a wrong "changed"
verdict is one already-bounded, already-gated extraction the system would have
run anyway. A wrong "unchanged" verdict would be the dangerous one, and the
subset rule makes it unreachable: a new hash always falsifies the subset. The
model-side `no significant changes` reply remains the second backstop for
semantic no-ops the hash cannot see, such as a volatile page whose bytes shift
but whose meaning did not.

## Why This Is A Workflow Gate

Per AGENTIC_BALANCE, determinism owns form and side-effects; model judgment owns
meaning. This gate compares HTTP validators and cryptographic hashes - pure
form, decidable from structure alone - and the only thing it controls is whether
to incur a paid side-effect. It never judges whether content is contradictory,
grounded, novel, or duplicative; those remain calibrated model judgments inside
the absorb pipeline, which still runs unchanged whenever the gate proceeds. A
hash is the antithesis of a brittle lexical rule: it cannot false-positive on
paraphrase or word overlap because it matches bytes, not meaning.

## Next Increment

RSS/Atom and sitemap `lastmod` hints are the next optional prefilter on top.
Treat feed timestamps as hints only; they may route which URLs to fetch first,
but content hashes and model or human judgment still own the final no-change and
meaning decisions.
