# Prepared consultation (S1) contract

Status: proposed design, 2026-09-24. Nothing here is implemented. It defines
the additive contract the [delivery plan](../plans/living-expertise.md#s1-prepare-before-consultation-with-bounded-temporary-evidence)
requires before S1 code. Prototypes wait for the frozen S0 protocol; the
default-on switch waits for S1's own exit evidence.

## Problem

Consultation today is stored-only. `consult_prompt.brief_synthesis_blocks`
opens with "Stored research only; no live check was performed" and
`synthesis_delivery` reports `freshness: stored_context_only`. Fresh context
exists only inside `expert sync --fresh-context`, which mutates the expert
through absorption. A caller asking a version-sensitive question therefore
gets the expert's last study, with honest disclosure but no current check.

## Where it plugs in

CLI `expert consult` and MCP `deepr_consult_experts` already share
`execute_consult_transaction`. Preparation runs there, before `run_consult`,
so both surfaces get identical behavior. Its output is one frozen packet that
`build_briefed_perspective` and `build_consult_context` receive as an extra
evidence layer, and that replaces the stored-only block with a dated
disclosure. Temporary sources live in an operation-scoped
`CorpusStore(storage_dir=...)`, never the canonical corpus.

## Flow and authority

1. **Scope** (code): question, caller identity, declared environment (for
   Python: interpreter version, platform, lockfile digest), information date,
   limits.
2. **Assumptions** (model): list the claims the answer would rest on and judge
   which need current evidence and why. The model owns this meaning; code
   validates the list's shape and caps its length. No keyword list decides it.
3. **Acquire** (code): for each checked assumption, fetch from the allowlisted
   source class for its kind, within source, byte, call, elapsed-time and
   capacity limits. Every attempt, including failures, consumes allowance.
4. **Study** (model): relate observations to stored positions; record
   conflicts as dated pairs (stored view, current observation), never as a
   silent override.
5. **Freeze** (code): write the packet, then answer from expert revision plus
   packet. Nothing canonical changes; proposals for learning are staged only.

## Packet (`deepr-prepared-context-v1`, proposed)

| Field | Meaning |
| --- | --- |
| `operation_id`, `caller_scope` | Identity; packets with private task context bind to one caller |
| `expert_revision` | Digest of the stored state the answer also uses |
| `question_sha256`, `environment` | What was prepared for |
| `assumptions[]` | Text, `checked` / `unchecked` / `not_needed` with the model's reason |
| `observations[]` | URL, request time, response `Date`, `Last-Modified`, ETag, SHA-256 of bytes, applicable version scope, status `ok` / `revalidated` / `failed` / `offline` |
| `conflicts[]` | Stored position id, current observation id, dated note |
| `implications[]` | Guidance affected, each linked to observations |
| `stop_reason`, `limits`, `attempts` | Complete / partial / failed / cancelled and why |
| `review_markdown_sha256`, `graph_sha256` | The dated Markdown review and graph projection, both rebuildable from this packet |

"No change found", "check failed" and "not examined" are distinct values.
A timestamp, empty search result or unchanged hash alone never yields
"current".

## Reuse

Reuse a packet only when caller scope, question assumption set, environment
digest and source set all match and every observation is within its class's
staleness allowance; otherwise revalidate with `If-None-Match` or
`If-Modified-Since`. A 304 records a new observation time without new bytes. A
changed hash triggers re-study of the affected assumption, not automatic
invalidation of the answer. Identical concurrent requests share one operation;
retries do not create fresh allowances.

## First source classes (Python exemplar)

Structured, keyless, free endpoints checked 2026-09-24, before any general web
search: PyPI JSON and PEP 691 Simple JSON for versions and yanks; OSV.dev
query and querybatch for advisories affecting pinned versions;
`peps.python.org/api/release-cycle.json` for interpreter support status.
GitHub's unauthenticated advisory API (60 requests per hour) and
endoflife.date are corroboration only. Official changelogs and "What's New"
pages are an allowlisted second tier through the existing pinned HTTP
transport. Details and limits: [practice review](../research/s0-s1-practice-2026-09-24.md).
SearXNG stays blocked under the current capacity policy.

## Acceptance evidence (from the delivery plan, made concrete)

- CLI and MCP produce the same packet for the same inputs and fixtures.
- Offline fixtures cover: a new release that changes advice, a new advisory
  for a pinned version, a yanked version, similar APIs with version-dependent
  behavior, contradictory references, unreachable sources, timeout,
  cancellation, duplicate requests, and denied cross-caller reuse.
- Deliberately stale sources, mismatched dates, missing links and an
  unsupported "up to date" claim fail the consistency check between packet,
  Markdown, graph and delivered context.
- Canonical expert files are byte-identical before and after.
- A separate paired preparation-on/off experiment from one expert revision,
  and a small dated live-source smoke. Neither is a longitudinal claim.

## Rejected alternatives

- **Running `sync --fresh-context` before consult:** mutates canonical state
  and is not scoped to the question.
- **General web search first:** unreproducible results and unprovable
  marginal cost; structured sources cover versions, advisories and support
  status authoritatively.
- **Confidence or recency as the trigger:** local text models expose no
  reliable internal signal, and file dates do not measure currency.
