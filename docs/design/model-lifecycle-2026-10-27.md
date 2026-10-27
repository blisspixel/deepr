# Model lifecycle repair, 2026-10-27

Status: implementation, 2026-10-27. Issue #292. Extends the
[lifecycle presentation](model-lifecycle-presentation.md) and the
[provider currency review](provider-currency-2026-10.md).

## Problem

Automatic selection trusted registry rows whose providers had dated their
shutdown. With only an OpenAI key, `AutoModeRouter._cheapest_available` and
`registry.get_cheapest_model()` returned `openai/gpt-4.1-nano`, which OpenAI
shut down on 2026-10-23: its row had `deprecated=False` and no deprecation
entry. Executable defaults still named shut-down or retiring ids
(`gemini-2.0-flash`, `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`,
`gpt-5`, `gpt-5-mini`, `o3`, `o4-mini`, `o4-mini-deep-research`,
`o3-deep-research`). The `prep` and `docs` planner choices held only GPT-5
snapshots and would advertise an empty list after 2026-12-11. The OpenAI and
Azure adapters expanded bare `o3`/`o4-mini` to shut-down deep-research ids,
which also swapped the priced contract.

## Sources (fetched 2026-10-27)

- [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations):
  `gpt-4.1-nano`, `gpt-4o-2024-05-13`, `o3-mini`, `o4-mini` shut down
  2026-10-23; `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `o3` shut down 2026-12-11
  (successors `gpt-5.6-sol`/`terra`/`luna`/`sol`); `gpt-4o`, `gpt-4o-mini`,
  `gpt-4.1`, `gpt-4.1-mini` shut down 2027-01-14 (OpenAI names
  `gpt-6-luna`); deep-research models shut down 2026-07-23 (`gpt-5.6-sol`).
- [OpenAI models](https://developers.openai.com/api/docs/models) and
  [pricing](https://developers.openai.com/api/docs/pricing): GPT-5.6 is no
  longer in the catalog page but is still served and priced; deep-research
  models are not listed.
- [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations):
  `claude-opus-4` and `claude-sonnet-4` retired 2026-06-15, `claude-opus-4-1`
  2026-08-05; `claude-sonnet-4-5` retires 2026-11-30. API version 2026-10-21
  removes `temperature`, `top_p` and `top_k`.
- [Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
  (updated 2026-10-22): `gemini-2.0-flash` shut down 2026-06-01; new projects
  are pointed at `gemini-3.8-flash` or `gemini-3.5-flash-lite`.
- [Azure Foundry retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule)
  (page date 2026-09-21): `o3`, `o3-deep-research`, `o4-mini` retire
  2026-11-19; GPT-5 family 2027-02-09; `gpt-4o` 2024-08-06/11-20,
  `gpt-4o-mini` and GPT-4.1 family 2027-04-14; `gpt-4o` 2024-05-13 2026-12-09.

## Decision

Reuse the existing lifecycle seams. No live provider-list checker is added.

- Registry rows for retired or retiring direct OpenAI ids become
  `deprecated=True` with a validated successor and a dated weakness note.
  Prices stay, because `registry_pricing` refuses unknown ids and historical
  ledger rows must still settle. A deprecated research row is refused before
  dispatch with its successor named. An explicit write-free preview may still
  price it, matching the existing `legacy_access_only` preview rule. Research
  dispatch therefore refuses the still-served GPT-5, `o3`, GPT-4o and GPT-4.1
  ids ahead of their shutdown dates; that earlier refusal is deliberate.
- `DEPRECATION_REGISTRY` gains dated entries with `auto_migrate=False`; an
  explicit choice is never silently replaced by a differently priced model.
  `o3` matches exact ids only so `o3-mini` keeps its own earlier date, and
  `gpt-4o-2024-05-13` has an exact 2026-10-23 entry ahead of the `gpt-4o`
  prefix. `is_shutdown` moves to `routing/deprecation.py` so the HTTP API can
  refuse dated shutdowns without importing the CLI.
- Automatic selection skips any direct-API id with a retirement record, in
  auto mode, registry selectors, saved benchmark rankings and the expert
  router; Azure rows follow the Azure schedule (see below). When
  nothing current remains, auto routing raises `AutoRoutingUnavailable` rather
  than returning a retired id; `route()` also refuses a fixed fallback that
  carries a non-migrating retirement record.

Defaults by role:

| Role | Was | Now | Why |
| --- | --- | --- | --- |
| Planning, review, lead, team design, doc review, grading, research fallback | `gpt-5`, `o3`, `o3-deep-research`, `o4-mini-deep-research` | `gpt-5.6-sol` | OpenAI successor; retained research default |
| Balanced reasoning (`docs` planner, `create_planner`, learner focus mode, chat/synthesis fallback chains, `gpt-4o`/`gpt-4.1` successor) | `gpt-5-mini`, `gpt-4.1`, `gpt-4o`, `o4-mini-deep-research` | `gpt-5.6-terra` | OpenAI successor for `gpt-5-mini` and `o4-mini` |
| Cheap utility (`UTILITY_MODEL`, chat follow-ups, map step, reflection, claim extraction/verification, validator, prompt refiner, context summary, benchmark probe) | `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-5-mini` | `gpt-5.6-luna` | These callers carry ceilings sized for mini-class prices (for example the $0.02 reflection ceiling and the cheap-only validator allowlist). Luna ($0.20/$1.20) matches that class; Terra ($2/$12) would multiply spend about eightfold. |
| Gemini env default | `gemini-2.0-flash` | `gemini-3.8-flash` | Google's new-project guidance; already selectable |
| `UnifiedConfig` default | `gpt-4o` | `gpt-5.6-sol` | Default only; stored values are not migrated |

Explicit historical ids stay accepted where they were (`ModelChoice`, planner
and validator allowlists, API allowlist) with lifecycle notices, until their
recorded date. The OpenAI and Azure adapters no longer expand bare `o3` or
`o4-mini`; those ids go out as themselves and meet the deprecation refusal.
Anthropic's adapter drops the three retired Claude ids from its supported list
and refuses them, their dated snapshots (for example
`claude-opus-4-1-20250805`) and the removed `claude-4-opus-legacy` alias,
instead of silently substituting the default model. These ids have no registry
pricing contract, before or after this change: `ANTHROPIC_PRICING` is an
unreferenced informational table, and `get_token_pricing` refuses them. No
ledger or reconciliation path re-prices Anthropic ids by name (ledger rows
store their settled cost), so no historical pricing path is added. Other dated
ids that are not registered (for example a current-model snapshot) still fall
back to the adapter default, as before; that pre-existing mapping is unchanged.

### Azure

Deprecation entries describe the direct OpenAI API. Azure Foundry keeps its own
schedule, so Azure rows stay selectable with their Azure dates stated, except
`azure-foundry/o3-deep-research`, which retires 2026-11-19 and is marked
deprecated. Deepr has no Azure GPT-5.6 contract to name as its successor.
Lifecycle lookups are provider-scoped: `check_deprecation(model, provider)` and
`is_shutdown(model, provider=...)` use `AZURE_DEPRECATION_REGISTRY` for the
`azure` and `azure-foundry` providers and the direct-API table otherwise.
Automatic selection keeps Azure rows until their Azure date (for example
`azure-foundry/gpt-4.1` until 2027-04-14), and the HTTP API applies the Azure
date when the request names an Azure provider. Azure is not execution-eligible
in any case.

### Prefix matching side effect

Retirement entries match dated snapshots by prefix, so unversioned family
members inherit a family date: `gpt-4o-transcribe` and `gpt-4o-realtime-preview`
report 2027-01-14 through `gpt-4o`, and `gpt-4o-mini-tts` and
`gpt-4o-mini-transcribe` through `gpt-4o-mini`. OpenAI's notice lists the dated
`gpt-4o` and `gpt-4o-mini` text snapshots, not these audio models. Deepr does
not register or call any of them (verified by search on 2026-10-27), so the
side effect is display-only; narrowing prefix matching is left for a change
that registers such a model.

### Learning cost estimates

Learner focus topics use `LEARN_FOCUS_MODEL` (`gpt-5.6-terra`) and campaign
topics `LEARN_CAMPAIGN_MODEL` (`gpt-5.6-sol`), in every learner path. The
focus-topic estimate and the minimum viable learning budget derive from the
registry `cost_per_query` of the focus model (now $0.25, floor $0.35 with the
$0.10 generation estimate); the campaign estimate keeps its conservative $2.50,
which exceeds the campaign model's registry cost. No rate is invented.

### GPT-5 request parameters

GPT-5 family models accept only the default temperature. A shared helper,
`providers/openai_params.py`, removes `temperature`/`top_p` and renames
`max_tokens` to `max_completion_tokens` for `gpt-5*` ids. The OpenAI research
adapter, task planner, context summary and expert chat utility calls use it;
the curriculum request no longer sends a temperature. Council synthesis keeps
its existing parameters and is out of scope here.

### Preview-only candidates are not promoted

OpenAI recommends `gpt-6-luna` for the GPT-4o and GPT-4.1 families. Deepr holds
it, with `gpt-6.1-sol` and `gpt-6-astra`, as `preview_only` in
`reviewed_catalog.py`. The 2026-10 currency review rejected promotion without
request, usage-settlement and adapter proof, and nothing since supplies that
proof. The GPT-4 family rows and notices therefore name the validated GPT-5.6
tier for the role and state that the OpenAI recommendation is preview-only.

## Anthropic sampling parameters

The direct Anthropic research adapter, Anthropic expert chat backend, council
synthesis and consensus paths send no `temperature`, `top_p` or `top_k`; the
chat backend strips them from caller extras. The pinned SDK sends its own
default `anthropic-version` (2023-06-01), so the 2026-10-21 removal does not
apply until that header changes. Not fixed here: the attended OpenRouter
completion sends `temperature: 0.2` with `require_parameters: true` for its
pinned `anthropic/claude-sonnet-5` route. Whether OpenRouter's Anthropic
endpoint accepts a non-default temperature for a Claude 4.7+ class model was
not verified; the likely failure is a refused route, not an unexpected bill.

## Unknowns and limits

- Account access to the GPT-5.6 tiers and `gemini-3.8-flash` was not checked.
- Request compatibility of GPT-5.6 with each caller's current parameters (for
  example `temperature` on chat-completions helpers) was not live-verified; no
  paid call was made.
- Deep research has no direct OpenAI successor model. `gpt-5.6-sol` is a
  general model, not a deep-research engine; research behavior and cost differ.
- Changing a calibrated grader or verifier model invalidates its earlier
  calibration until it is re-measured.
- The 2027-01-14 and 2026-12-11 dates are recorded deadlines. CLI choice
  lists drop members on those dates; registry rows are already deprecated.

## Verification

Offline tests cover dated entries and prefix precedence, unchanged explicit
identity, registry deprecation with successors, selectors and auto routing that
never return a retired id, fail-closed routing with only retired candidates,
benchmark-file filtering, current defaults by role, the Gemini env default,
non-empty planner choices after 2026-12-11, API refusal of shut-down
allowlisted ids, Anthropic refusal, and historical pricing for every retired id.
