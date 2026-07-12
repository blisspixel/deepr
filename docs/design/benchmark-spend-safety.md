# Benchmark Spend Safety

Status: historical v2.34.1 design, superseded for execution by the v2.36
fail-closed release gate. Dry-run and saved-artifact reads remain available.

## Problem

`scripts/benchmark_models.py` can call provider and judge models directly. Its
historical `--budget` check ran after every evaluation future had already been
submitted, judge calls did not consume that budget, and benchmark spend did not
write the canonical append-only ledger. The dashboard therefore could not
truthfully treat an approved estimate as a runtime ceiling.

## Restoration Contract

Live provider benchmarks are disabled in v2.36. The following describes the
minimum transaction required before they can be re-enabled; the existing
benchmark-specific reservation substrate is not a works-now execution claim.

Every benchmark evaluation, judge, and provider-validation call must reserve a
conservative call ceiling before it is submitted. Reservation uses the existing
durable cost-reservation store, so configured daily and monthly limits include
other processes and in-flight work. A run-local guard also rejects reservations
that would exceed the operator-approved benchmark ceiling.

The provider adapters used by this script do not expose one consistent usage
shape. Until they do, successful and ambiguous calls settle at the conservative
reserved ceiling and record that basis in ledger metadata. This may overstate
spend, but it cannot create a silent-money path. A definite failure before a
provider call may refund its reservation. Ledger persistence completes before
the durable hold closes.

Each ceiling mirrors the maximum output-token field sent by its adapter. OpenAI
Responses calls set `max_tool_calls`, and Gemini 2.5 grounding adds the documented
per-grounded-prompt charge. OpenAI search estimates cover a full model context
window for each permitted tool call, plus a pricing multiplier for long-context
and regional uplifts. Pricing or context metadata that is absent or invalid
fails closed.

Managed OpenAI and Gemini deep-research agents are excluded from paid benchmark
execution because their autonomous loops do not expose a deterministic
request-level token and tool ceiling. Gemini 3 search grounding is also excluded:
one request can issue multiple separately billed searches, and the provider does
not document a per-request query cap. The research tier uses bounded web-search
orchestration instead. xAI search is excluded because `max_turns` does not bound
parallel billable tool invocations within a turn. Grok 4.3 was part of the
historical chat-tier adapter set, but is not a live v2.36 benchmark execution
path.

The scheduler may retain bounded parallelism, but only futures with completed
reservations may be submitted. Evaluation and judge work share one run ceiling.
The default preflight cap becomes the runtime ceiling when `--budget` is absent.
`--no-cost-cap` cannot authorize an unbounded paid run: a finite `--budget` is
still required. Dry runs, prompt display, and ranking regeneration remain `$0`
and do not write spend events.

## Rejected Alternatives

- Checking accumulated results after futures complete was rejected because
  already-submitted calls can spend beyond the ceiling.
- Writing one aggregate event after the run was rejected because interruption
  can lose spend and individual provider calls would remain unauditable.
- Treating fixed cost assumptions as provider-reported usage was rejected. The
  ledger records them explicitly as conservative ceilings until adapters expose
  normalized usage.
- Allowing managed research agents under an average-job estimate was rejected
  because an average cannot enforce a hard spend ceiling.
- The v2.34 design rejected disabling all benchmarks. v2.36 supersedes that
  choice because benchmark calls must use the same shared durable transaction
  as other provider work before live execution resumes.

## Verification Required Before Re-enablement

- No future is submitted without a reservation.
- Evaluation, judge, and validation calls consume the same finite run ceiling.
- Reservations that would exceed run, daily, or monthly ceilings block before
  the provider call.
- Every submitted call settles one idempotent ledger event, including ambiguous
  failures at the reserved ceiling.
- Ledger write failure prevents further scheduling and leaves the durable hold
  available for reconciliation.
- Tests use injected calls and isolated cost paths. They never call a provider.

## Current Provider Evidence

Reviewed 2026-07-10:

- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) prices web
  search per tool call and bills retrieved search content at model token rates.
- [xAI pricing](https://docs.x.ai/developers/pricing) prices web search per tool
  invocation, while its [tool-use guide](https://docs.x.ai/developers/tools/tool-usage-details)
  documents parallel tool calls within `max_turns`.
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) prices
  Gemini 2.5 grounding per prompt, Gemini 3 grounding per generated query, and
  managed agents by underlying loop token and tool consumption.
