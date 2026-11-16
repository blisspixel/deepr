# Model currency, 2026-11-15 (#328)

Decision before implementation: move new-request defaults, allow-lists, and
advertised CLI choices onto the current public model ids. Keep historical
registry, changelog, and pricing rows so old records can still be priced or
refused. Do not silently rewrite an explicit historical id. Do not change
embedding models. Do not enable a new metered dispatch path.

## Current ids

- OpenAI research default: `gpt-6.1-sol` ($2 input, $0.10 cached, $10 output
  per million tokens). Balanced: `gpt-6.1-terra` ($1 / $0.05 / $5). Cheap
  utility: `gpt-6-luna` ($0.10 / $0.01 / $0.50). Explicit flagship, not the
  silent default: `gpt-6-astra` ($10 / $1 / $50). These four are selectable.
  `gpt-6-sol` stays a priced preview row because its cache hit ($0.20) is a
  different contract from `gpt-6.1-sol`.
- xAI flagship alias target: `grok-4.7` ($2 input, $6 output). Cached input
  $0.50 is carried from the 2026-11-03 review; the models page snippet used
  for this pass did not restate the cache rate. `grok-4.6` stays priced.
  Bare `grok-4` leaves new-request allow-lists.
- Gemini Pro alias target: `gemini-4-carbon`. Stored rates are the December 1,
  2026 caps, $4 / $20 / $0.20, matching the existing Argon conservative row.
  Introductory rates through November 30, 2026 are $2 / $10 / $0.10. Flash
  stays `gemini-3.8-flash`. Lite stays `gemini-3.5-flash-lite`.
- Anthropic new-request set: `claude-opus-5-5` ($4 / $20, cache read $0.20),
  `claude-sonnet-5-5` ($2 / $10, cache hit $0.10), `claude-haiku-5-5` (kept at
  the over-100,000-token tier $0.50 / $2.50), and `claude-fable-5-2` ($8 / $40,
  5-minute cache write $10, 1-hour write $16, cache read $0.20).
  `claude-fable-5-1` stays preview-only. Retired Claude ids stay refused
  rather than swapped. Limited-access Mythos models stay out.

GPT-5.6 rows stay in the registry and are not mass-deprecated. Deprecation
successor text for already-retired OpenAI ids names the GPT-6 role, with
`auto_migrate` left false. Registry `cost_per_query` for the promoted rows
uses the existing query-scale overrides (Luna 0.05, Terra 0.15, Sol 0.30,
Astra 1.50) so automatic cheapest-selection does not collapse onto a
formula-scale Luna price. Token billing still uses the per-million rates.

Chat sampling for GPT-6 follows the GPT-5 rule: omit `temperature` and
`top_p`, and send `max_completion_tokens`. This does not migrate callers to
the Responses API.

## Advertised surfaces

CLI choices, dashboard research and settings choices, and `PATCH /api/config`
`default_model` use the four current OpenAI ids. Help text names the current
provider ids. A saved default outside that list is rejected before any other
configuration field changes. Explicit GPT-6 and retained GPT-5.6 research ids
stay on the OpenAI deep-research provider when the caller does not name one.

## What stays refused

Shut-down ids, including `o3-deep-research`, `o4-mini-deep-research`, and the
dated Sonnet 4.5 snapshot, are refused before an allow-list miss. Advertised
CLI choices hide them. Explicit historical input still echoes the id and the
recorded notice. OpenRouter preview rows, plan-quota adapters, and unattended
metered dispatch stay blocked.

## Toolchain and pins

Managed CPython moves to 3.15.2 and uv to 0.13.8 because uv 0.13.5 has no
3.15.2 download. See [maintained runtime support](maintained-runtime-support.md).
`soupsieve` is locked at 4.1.1 through the existing `beautifulsoup4`
dependency, which requires Python >=3.11.5. The dashboard `minimatch`
override is 11.0.8. Neither pin adds a direct dependency. Embeddings stay on
`text-embedding-3-small` and the existing local profiles.

## Rejected alternatives

- Leaving GPT-6 preview-only would keep new requests on superseded GPT-5.6 ids.
- Using Astra as the silent default would raise the default research price
  from the Sol contract to $10 / $50.
- Pricing Carbon at the introductory $2 / $10 rate would understate the
  December 1 cap.
- Replacing `text-embedding-3-small` would require a vector rebuild.
- Adding `soupsieve` or `minimatch` as direct dependencies is unnecessary.
- Deleting historical price rows would make old ledger records unpriceable.

Primary sources:

- <https://developers.openai.com/api/docs/models>
- <https://docs.x.ai/developers/models>
- <https://aistudio.google.com/docs/models>
- <https://aistudio.google.com/docs/pricing>
- <https://platform.claude.com/docs/en/about-claude/pricing>
- <https://github.com/astral-sh/uv/releases/tag/0.13.8>
- <https://www.python.org/downloads/release/python-3152/>
