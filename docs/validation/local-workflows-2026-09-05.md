# Local workflow validation - September 5, 2026

The local CLI and MCP workflows completed at $0 marginal API cost. The built
web application created a local profile and exposed retained expert state.
Quota execution remains unverified because the provider rate-limited its
account-control endpoint. OpenRouter validation was read-only; no paid
inference request was made.

## Scope and evidence

CLI runs used main commit `1d73f28675f7900462ff9d37e109629a4743f7de`.
The dashboard checks used the v2.50.13 candidate, its production frontend build,
and the actual Flask backend. The existing Temporal Knowledge Graphs expert
was copied into an isolated workspace before modification. A before/after
hash inventory checks that its canonical source files remain unchanged.

The saved evidence lives under the configured reports root in
`validation/live-workflows-2026-09-05`. It includes the manifest, CLI outputs,
source snapshot metadata, MCP contract result, web checks, and file hashes.
Release packaging and installer evidence is recorded separately after the
exact green main commit is tagged.

| Workflow | Observed result | Limit of the evidence |
| --- | --- | --- |
| Create and retain | Created Deepr Evidence Reviews with a local model and retained the source-bound value-loop design note. | Profile creation performs no learning. One source is not corroboration. |
| Local study | Two lenses completed with Gemma `gemma4:e2b`: 14 findings, 13 marked grounded. | The grounding label is a model assessment, not a reviewed truth label. |
| Local brief | Generated a consultable brief at $0 with explicit evidence limitations. | No blinded quality comparison was performed. |
| Existing expert update | Absorbed the primary XTDB time documentation into the isolated temporal-expert copy: 14 of 19 candidates added, 5 refused by grounding checks. | Additions and refusals require calibrated semantic review. Counts alone do not show improvement. |
| Two-expert MCP consultation | Two stored perspectives and one local synthesis completed; all 15 contract checks passed. | This is in-process MCP tool validation, not autonomous agent dialogue or remote-host qualification. |
| Built web application | Created an untrained local profile, opened actual claims, verified study counters, checked local CLI handoff, blocked chat, and 320px reflow. | Only the isolated expert workspace was mutated. |
| Quota provider | Account-control observations returned rate limits, including a one-hour retry interval. No quota inference was dispatched. | Stored authentication alone does not prove current executable capacity. |
| OpenRouter | All seven public route checks passed; current-key controls remained ineligible under the monthly, BYOK-inclusive $5 policy. | Metadata and account inspection grant no dispatch authority. |

External paid API spend for this validation session was **$0**, within the
user's total $10 ceiling. The stricter repository quarantine remained binding.
No account limit, payment control, credential authority, or routing default was
changed to obtain a successful result.

## Regressions found and corrected

- Failed quota probes returned exit 0 in JSON mode.
- Web-created profiles inherited an API provider and positive learning budget.
- A new profile remained hidden behind the flagship roster or a name filter.
- Shared link buttons crashed when passed through Radix Slot.
- Search re-rendering lost keyboard focus; non-link expert cards excluded
  keyboard users; a profile parameter was decoded twice.
- Inherited object property names were accepted as persisted accents.
- The expert detail response omitted study metadata, showing zero findings.
- A knowledge-count read created a belief directory for an untrained expert.

Focused tests reproduced the defects before correction. The frontend has 77
passing behavioral tests and 66 isolated browser checks across light and dark
themes at 320, 390, and 1440px. The brand checks exercise actual 16-32px marks
and 192 filled-control color/state combinations; their minimum measured text
contrast was 5.12:1. This is targeted verification, not a whole-app
accessibility certification.

The committed browser regression script is
[`qa/local-ui.mjs`](../../src/deepr/web/frontend/qa/local-ui.mjs), run by CI.
Its data is explicitly synthetic, every API and socket request is intercepted,
and it refuses nonlocal traffic. README screenshots instead come from the
actual built dashboard and the isolated live workspace described above.

## Next decision

The next useful increment is the v2.51 source-world preflight: verify nested
source hashes and cutoffs, materialize equal inventories into isolated arms,
record effective model and memory context, and bind blinded reviewer packets
to exact answer bytes. Then run the four-arm longitudinal comparison and
review false support, false refusal, stale reuse, effort, and outcomes
separately. No unreviewed aggregate score should choose a winner.

This ordering follows the [active roadmap](../../ROADMAP.md),
[harness research](../design/agent-harness-lessons-2026.md), and
[local-first runtime proposal](../design/local-first-agent-runtime-options.md).
Hosted agents remain an optional future companion to locally owned expert
state, after value, ownership, recovery, and cost boundaries are proven.

Primary temporal source:
[Time in XTDB](https://docs.xtdb.com/about/time-in-xtdb.html), retrieved
September 5, 2026. The source snapshot and extracted text hashes are retained
with the local evidence; derived expert artifacts were not hand-edited.
