# Provider currency review, 2026-10-06

## Problem and evidence

The August registry describes several models as current after their providers
have released successors. Retaining a model name does not establish that its
request parameters, cache accounting, or tool behavior are compatible with
Deepr. A currency update must preserve that distinction and the existing paid
dispatch quarantine.

Primary documentation reviewed on 2026-10-06:

- [OpenAI models](https://developers.openai.com/api/docs/models),
  [pricing](https://developers.openai.com/api/docs/pricing), and
  [Python SDK](https://developers.openai.com/api/reference/python).
- [Claude models](https://platform.claude.com/docs/en/models/overview),
  [pricing](https://platform.claude.com/docs/en/about-claude/pricing), and
  [Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python).
- [Gemini models](https://ai.google.dev/gemini-api/docs/models) and
  [pricing](https://ai.google.dev/gemini-api/docs/pricing).
- [xAI models](https://docs.x.ai/developers/models) and
  [release notes](https://docs.x.ai/developers/release-notes).
- [Azure catalog](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
  and published SDK package dependency metadata.

## Decision

Add a named reviewed-release catalog for the newest public text models. It
owns dated metadata for candidates awaiting adapter and settlement validation,
separately from the established routing entries and OpenRouter route proposals.
Candidates enter the existing registry with `preview_only=True`; the automatic
selectors continue excluding them. Direct registry selectors now also exclude
deprecated entries, matching automatic routing's existing filter. Historical
price lookup remains available. Candidate registration changes no defaults,
model request policies, Azure deployments, frozen evaluation arms, or spend
permissions. Published
provider capabilities are observations, not demonstrated quality in Deepr.

Correct verified GPT-5.6 token prices without changing aliases. Keep Gemini
Flash estimates at the published January 2027 rates as conservative caps;
document the temporary discount rather than encoding it as a permanent rate.
Use the higher Grok long-context rate at the existing conservative 200K
boundary. Per-query candidate estimates use 10K input plus 1K output tokens;
latency is explicitly an unmeasured placeholder and cannot rank candidates.

Migrate to the current OpenAI 3.26, Anthropic 1.11, Google GenAI 2.28, and Azure
AI Projects 2.8 SDKs. OpenAI and Anthropic require HTTPX2 custom clients. Declare
HTTPX2 directly for those adapters and the local OpenAI-compatible Ollama seam;
keep HTTPX for Google and existing raw HTTP adapters. Global package aliasing
is rejected because it would silently change unrelated transports and mocks.
Preserve endpoint guards, disabled ambient proxies and redirects, zero SDK
retries, local cloud-disable checks, and header sanitation. Extend the paid
boundary checker to recognize HTTPX2 rather than let the new import bypass it.
Test real SDK serialization and status handling through mock transports without
network dispatch. Retain Azure AI Agents' existing preview pin rather than
downgrading it to the latest stable 1.1 release; it is a separate agents API.

The no-key OpenRouter check found six eligible proposals and one refused
DeepSeek proposal. Public metadata no longer contains its pinned `deepseek`
endpoint. Preserve refusal and record the route-review backlog; choosing a
different provider without accounting evidence would change the contract.

The dependency audit also flagged existing multidict, PyJWT, urllib3,
virtualenv, and Werkzeug pins. Compatible updates resolve the audit without
adding advisory exceptions: 6.9.1, 2.15.1, 2.8.0, 21.14.5, and 3.1.9,
respectively. Virtualenv also updates python-discovery to 1.6.1. This is a
dependency remediation, not a claim that every advisory was exploitable through
Deepr. References include the publishers' [multidict advisory](https://github.com/aio-libs/multidict/security/advisories/GHSA-54p9-h82j-f925),
[PyJWT releases](https://github.com/jpadilla/pyjwt/releases/tag/2.15.1),
[urllib3 release](https://github.com/urllib3/urllib3/releases/tag/2.8.0),
[virtualenv advisory](https://github.com/pypa/virtualenv/security/advisories/GHSA-p58f-9548-mpm2),
and [Werkzeug advisory](https://github.com/pallets/werkzeug/security/advisories/GHSA-g6x2-hccm-hh4m).

## Budget identity and settlement corrections

The final budget review reproduced four existing accounting defects. Pricing
lookup accepted arbitrary substrings as registered model identities, including
unknown future variants and foreign gateway slugs. Restrict compatibility to
exact registered identities, finite aliases, and anchored numeric snapshot
suffixes (including the existing Grok date-before-mode form). Unknown variants
must not inherit a cheaper family's pricing or dispatch contract. Historical
registered prices and supported snapshots remain available.

The attended OpenRouter caller clipped an over-hold `usage.cost` to the reserved
amount. Pass the full reported charge to the existing durable settlement seam,
which records the overrun, freezes paid authority, and raises a divergence.
Translate that error to a Click failure; never publish an overrun as a successful
report. The current [OpenRouter routing contract](https://openrouter.ai/docs/guides/routing/provider-selection#max-price)
also places token price limits under `provider.max_price`, while the caller
emitted them at the top level. Correct the nesting and test the serialized POST
body with cache-off headers and redirects disabled. Admission ceilings remain
unchanged. Test the real ledger and durable
reservation with synthetic dispatch, including a normal-charge control and a
subsequent refused reservation. No inference request is needed.

The operator ceiling parser also accepted `NaN`: its range comparisons are
false for that float. Require finiteness before accepting a deliberate ceiling
raise, keeping the documented default for unusable input. Exercise NaN,
infinities, valid lower limits and valid higher limits through the existing
ceiling regression cases.

The current-key and spend-control documentation was also reviewed on
2026-10-06. The required `/key` fields and BYOK-inclusive monthly-key policy
remain supported. New workspace/guardrail budgets are additional provider
stops, not replacements admitted by Deepr's key-bound verifier. A shared
workspace budget does not prove a per-key monthly ceiling or invoice total.
Unattended dispatch remains quarantined. See [current-key schema](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key)
and [spend controls](https://openrouter.ai/docs/guides/best-practices/spend-controls).

## Hosted CI dependency and packaging follow-up

The first candidate's hosted frontend audit exposed Axios, brace-expansion and
source-map-js advisories. Update those within compatible ranges. Three parent
packages still pin vulnerable transitive releases: Tailwind typography uses
selector-parser 6.0.10, and rehype-katex plus micromark math use KaTeX 0.16.x. Use a scoped
selector-parser override for Tailwind and an explicit override for the shared
KaTeX dependency, at 7.1.6 and 0.18.2 respectively, the published patched
versions. Downgrading the parent plugins to obsolete versions is rejected.
Verify the typography consumer's selector API, Markdown math rendering, and
KaTeX trust refusal as well as the existing build and browser checks. The
Python dependency audit alone does not qualify the frontend dependency tree.
References: [Axios release](https://github.com/axios/axios/releases/tag/v1.20.0),
[selector-parser advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf),
[source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q), and
[KaTeX advisory](https://github.com/advisories/GHSA-238p-pmpm-9mq7).

Hosted plugin validation also exposed a checksum generated from CRLF working
bytes that Git normalizes to LF. Regenerate the package checksum from its
mandated LF content, then verify the archive on both platforms. No checksum
validation is relaxed.

## Alternatives and validation

Changing all defaults to the newest names would confound the frozen continuity
comparison and imply untested request compatibility. Adding unrestricted
gateway routes or weakening endpoint uniqueness would change billing authority.
Both are rejected. A catalog-only update gives an inspectable inventory while
leaving promotion conditional on parameter and settlement proof.

Verify exact candidate identity and price lookup, cache and long-context
boundaries, exclusion from automatic selectors, and stable aliases. Run the
full offline unit suite and combined coverage gate on the updated lock, lint,
format, strict types, ratchets, docs consistency, and paid-boundary checks.
No paid provider request is part of this review. Passing these checks does not
qualify the new models' advice or establish hosted CI success.
