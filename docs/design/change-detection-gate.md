# Pre-sync change-detection gate (content-hash slice)

Status: design note, 2026-06-23. Implements the first slice of the Phase 4d
"pre-sync change-detection gate" roadmap item. Cross-references
[capacity-waterfall.md](capacity-waterfall.md) (the $0-first routing this serves)
and [../plans/AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) (why this is a
workflow gate, not a meaning verdict).

## Problem

`deepr expert sync` researches each due subscription and then absorbs the answer
into beliefs through the verification-gated pipeline. Absorption runs a paid
extraction model call. In practice a large fraction of refresh runs find nothing
new: the same release page, the same docs, the same sources as last time. Today
two gates already skip that paid absorb - `_fresh_context_has_no_sources` (the
retrieval found nothing) and the model-side `no significant changes` reply. Both
sit *after* retrieval. Neither catches the most common case cheaply: retrieval
succeeded and returned the **byte-identical sources** it returned last sync, so
there is provably nothing new to absorb.

## The signal

A content hash of each fetched source's extracted main content. ETags and
`Last-Modified` are advisory and server-dependent; a content hash is universal
and authoritative - it is the 2026 best-practice fallback precisely because a
page re-saved with identical bytes keeps the same hash even when its timestamp
moves. We hash the extracted main content (not raw HTML, not the search snippet)
because that is the text the absorber actually reads.

`FreshSource.content_hash` is a derived property (`sha256` of the stripped
content) so the hash can never drift from the content it summarizes. It is
persisted per source in both `FreshContext.to_source_pack()` and
`to_metadata()`, which means every sync already writes the validators the next
sync needs - no new datastore, reusing the existing
`sync_artifacts/source_packs/*.json` artifacts.

## The gate

`fresh_sources_unchanged(prior, current)` in `experts/sync.py` is a pure,
deterministic function over the two source-pack dicts. It returns `True` only
when every content hash in the current retrieval already appeared in the prior
sync's pack (current hashes are a subset of prior hashes) - i.e. the run added
no new content. `_sync_subscription` loads the most recent prior pack for the
topic *before* writing the current one, and when the gate fires it records a
`no_changes` outcome and skips the paid absorb, exactly like the existing gates.

## Fail-safe direction (no brittle failure mode)

The gate fails safe **toward proceeding**, never toward skipping. It returns
`False` (treat as changed, run the normal pipeline) whenever it cannot *prove*
no-change:

- no prior pack exists (first sync, or a new topic),
- the current run produced no hashable content (fetch failures, snippet-only
  sources),
- any current hash is absent from the prior pack (new or changed source),
- a prior artifact is unreadable, or sources predate this feature and carry no
  `content_hash`.

So a real update is never silently dropped. The only cost of a wrong "changed"
verdict is one already-bounded, already-gated extraction the system would have
run anyway. A wrong "unchanged" verdict would be the dangerous one (a frozen
expert), and the subset rule makes it unreachable: a new hash always falsifies
the subset. The model-side `no significant changes` reply remains the second
backstop for semantic no-ops the hash cannot see (e.g. a volatile page whose
bytes shift but whose meaning did not).

## Why this is a workflow gate, not a meaning verdict

Per AGENTIC_BALANCE, determinism owns form and side-effects; model judgment owns
meaning. This gate compares cryptographic hashes for exact equality - pure form,
decidable from structure alone - and the only thing it controls is whether to
incur a paid side-effect. It never judges whether content is contradictory,
grounded, novel, or duplicative; those remain calibrated model judgments inside
the absorb pipeline, which still runs unchanged whenever the gate proceeds. A
hash is the antithesis of a brittle lexical rule: it cannot false-positive on
paraphrase or word overlap because it matches bytes, not meaning.

## Next increment (not in this slice)

Conditional GET. Persisting `etag` / `last_modified` per source and sending
`If-None-Match` / `If-Modified-Since` on the next fetch lets the server answer
`304 Not Modified` with no body transfer, moving the skip *before* retrieval
cost rather than before absorb cost. That needs a pre-research probe loop over
known URLs and HTTP-header plumbing through the fetcher, so it ships as its own
change with its own consumer (YAGNI: no validator plumbing lands until the probe
that reads it). RSS/Atom and sitemap `lastmod` hints are a further optional
prefilter on top.
