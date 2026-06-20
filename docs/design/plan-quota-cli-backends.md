# Plan-quota CLI backends

Status: design + first implementation, 2026-06-20. Implements the ROADMAP
Phase 6 "CLI provider adapters" rung of the capacity waterfall
([capacity-waterfall.md](capacity-waterfall.md)). Governs how Deepr drives a
vendor's own coding/agent CLI as a research backend without producing a surprise
bill. Read [AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) first - this is a
textbook "determinism on the money side-effect, model judgment on meaning"
surface.

## The bet, and the honesty test

Phase 6's promise is "your existing subscriptions become research capacity": a
flat monthly plan you already pay for runs Deepr's non-urgent, batchable
maintenance (scheduled `expert sync`, gap-fill, health-check) at **$0 at the
margin**, before any metered API dollar. That promise only holds for a CLI where
the marginal request inside the plan window is genuinely free. So every
candidate CLI is run through one test:

> Is the next headless call free at the margin on a flat subscription, or does it
> bill per use?

A CLI that bills per use is just the metered API wearing a CLI costume - it earns
no place as "free capacity". The June-2026 survey:

| CLI | Headless cmd | $0 at margin on a flat plan? | Auto-routable | Why |
|---|---|---|---|---|
| Codex (`codex exec`) | yes | yes, within 5h/weekly window | **yes** | flat ChatGPT plan |
| Claude Code (`claude -p`) | yes | yes (Jun-15 credit-pool change was paused) | **yes** | plan rolling window |
| OpenCode (`opencode run`) | yes | yes if routed to an OAuth/local provider | **yes** | BYO-provider, MIT |
| Kiro (`kiro-cli chat`) | yes | yes (monthly credits, overage off by default) | no | ToS prohibits third-party-harness use |
| Grok Build (`grok -p`) | yes | subscription quota, but gray | no | xAI steers automation to the metered key |
| Antigravity (`agy -p`) | brittle (non-TTY stdout drop) | weekly hard-stop | no | active automation ban wave + stdout bug |
| Copilot (`copilot -p`) | yes | **no** - usage-based since 2026-06-01 | no | metered per token |

"Auto-routable" means Deepr's waterfall may *automatically* select it. The rest
are supported via an explicit `--plan <id>` only, behind the safety gate and a
printed ToS/billing note - never auto-selected, never marketed as free.

## Two seams, one chosen

Deepr has two execution seams. The heavy `DeepResearchProvider` contract
(submit/poll/vector-stores) is API-shaped and wrong for a subprocess CLI. The
light `research_fn` seam - `(query, budget) -> {"answer", "cost", ...}`, the same
one the local Ollama backend uses - is exactly right and is what the flagship
payoff (scheduled expert maintenance) flows through.

`expert sync` does both research *and* verified belief extraction. A CLI is not
an OpenAI client, so to run the **whole** sync on prepaid capacity (no silent
metered extraction) the adapter is exposed as a `PlanQuotaChatClient`: it
satisfies the minimal `client.chat.completions.create(model=, messages=) ->
.choices[0].message.content` surface every Deepr chat seam already uses, exactly
like `ollama_chat_client`. One client instance serves research and the
`ReportAbsorber`, so the entire loop runs on the plan.

## The deterministic safety gate (no-surprise-bills)

Money side-effects are gated deterministically; nothing here judges answer
quality. Before any subprocess runs (`safety.evaluate_plan_quota_safety`):

1. **Auth mode must be plan, not a metered API key.** If a backend's metered-env
   var is set (`OPENAI_API_KEY`/`CODEX_API_KEY` for codex, `ANTHROPIC_API_KEY`
   for claude, `XAI_API_KEY` for grok, ...), the next call would bill that key on
   every vendor's precedence rules - so the gate **blocks** and tells the
   operator to unset it or use `--api` on purpose. (`codex doctor` /
   `codex login status` can confirm the *stored* mode too, but env presence is
   the decisive, deterministic signal.)
2. **A metered-at-margin CLI requires explicit acknowledgement.** Copilot is
   `metered_at_margin=True`: it is off by default and, when invoked, the CLI asks
   before spending. A paid call is never a side effect.

Every call also writes the append-only ledgers: a `quota_ledger.jsonl`
observation (usage, or a terminal `EXHAUSTED` event when the CLI signals a
depleted plan) and a `$0` `cost_ledger.jsonl` event with the quota units in
metadata, so `costs show` and anomaly detection see volume even at $0 marginal
cost. The cost ledger stays the single record of every spend source.

## Why auto-routing stays gated off by default

The waterfall's plan-quota rung (`choose_maintenance_backend`) only auto-selects
a CLI that is installed, in plan auth mode, ToS-clean (`enabled_by_default`), and
has an **observed, non-exhausted remaining-quota window**. Vendor CLIs do not
expose trustworthy remaining quota, so `remaining_confidence` is recorded as
`UNKNOWN` and the eligibility gate returns `QUOTA_UNKNOWN` - i.e. not
auto-routed. This is deliberate: auto-routing maintenance onto a plan window the
operator is also using interactively would silently exhaust it. Until a probe
can record a trusted remaining signal, the **explicit** path is how operators opt
in:

- `deepr expert sync NAME --plan codex` - run this sync on the plan now.
- `deepr capacity probe-plan codex` - validate auth + one round-trip ($0 on a
  subscription; asks first for a metered CLI).

`choose_plan_quota_backend` resolves an explicit request through the same safety
gate but without the observed-quota requirement (the operator chose it).

## What is deterministic vs model judgment (AGENTIC_BALANCE)

| Concern | Setting |
|---|---|
| auth-mode detection, overage/ack gate, exhaustion handling, quota+cost ledger writes, argv construction, tool lockdown (`--deny-tool`/read-only sandbox), scratch cwd | **workflow** (deterministic, gated) |
| the research answer and the extracted beliefs | **agent** (model), then through the existing absorb gates: confidence floor, source-trust ceiling (research-derived = tertiary, capped), contradiction + dedup verdicts |

The plan CLI is an answer generator on the cheap-capacity side of the waterfall;
every claim it produces still passes the same verification gates as any other
source. The trust-floor ceiling means even an imperfect extraction cannot mint a
high-confidence belief.

## Known follow-ups

- Live quota probes that record a *trusted remaining* signal would let the
  auto-routing rung light up for codex/claude/opencode (today: explicit only).
- `deepr capacity` detection ids are exe-based (`kiro-cli`, `agy`) while
  execution ids are canonical (`kiro`, `antigravity`); the capacity quota display
  for those two does not yet join to execution-recorded usage. Cosmetic.
- Antigravity headless needs a PTY wrapper (non-TTY stdout drop); the adapter
  detects empty output and errors with that hint rather than silently passing.
- OpenCode is BYO-provider: today the safety gate treats it as plan-clean, but a
  per-run check of the resolved provider's `auth.json` `type` (oauth vs api)
  would make "don't bill a metered provider" enforcement exact.
