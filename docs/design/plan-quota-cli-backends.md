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
maintenance and expert bootstrapping (`expert sync`, `expert absorb`, topic
`expert learn`, `learn-web`, gap-fill, health-check) at **$0 at the margin**, before any metered
API dollar. That promise only holds for a CLI where the marginal request inside
the plan window is genuinely free. So every candidate CLI is run through one
test:

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
| Antigravity (`agy -p`) | yes (answer read from transcript, not stdout) | weekly hard-stop | no | active automation ban wave |
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

`expert sync` and topic `expert learn` both perform model synthesis and verified
belief extraction. A CLI is not an OpenAI client, so to run the **whole** run on
prepaid capacity (no silent metered extraction) the adapter is exposed as a
`PlanQuotaChatClient`: it satisfies the minimal
`client.chat.completions.create(model=, messages=) ->
.choices[0].message.content` surface every Deepr chat seam already uses, exactly
like `ollama_chat_client`. One client instance serves synthesis and the
`ReportAbsorber`, so the entire loop runs on the plan. The same client backs the
multi-expert **consult** synthesis seam (`ExpertCouncil`), so an external agent
can run a whole fan-out consult on prepaid capacity.

**Prompt delivery is over stdin, not argv.** A multi-line prompt (a synthesis
prompt with several experts' perspectives, a long report) passed as a
command-line argument to a `.cmd` shim is mangled by `cmd.exe` on Windows: the
child sees an empty task and answers conversationally at $0 - a silent quality
failure, not an error. Codex and Claude therefore set `stdin_prompt=True` and
receive the prompt on stdin (`codex exec -` / `claude -p -`). Any plan adapter
that may receive long or multi-line prompts should do the same.

## The deterministic safety gate (no-surprise-bills)

Money side-effects are gated deterministically; nothing here judges answer
quality. Before any subprocess runs (`safety.evaluate_plan_quota_safety`):

1. **Child auth mode must be plan, not a metered API key.** If a backend's
   metered-env var is set (`OPENAI_API_KEY`/`CODEX_API_KEY` for codex,
   `ANTHROPIC_API_KEY` for claude, `XAI_API_KEY` for grok, ...), a normal CLI
   launch could bill that key on vendor precedence rules. Deepr therefore
   removes those known metered vars from the child environment first, records
   that sanitization in the safety reason, and evaluates the sanitized child
   env as the plan path. (`codex doctor` / `codex login status` can confirm the
   stored mode too, but the child env is the deterministic launch contract.)
2. **A metered-at-margin CLI requires explicit acknowledgement.** Copilot is
   `metered_at_margin=True`: it is off by default and, when invoked, the CLI asks
   before spending. A paid call is never a side effect.

Every call also writes the append-only ledgers: a `quota_ledger.jsonl`
observation (usage, or a terminal `EXHAUSTED` event when the CLI signals a
depleted plan) and a `$0` `cost_ledger.jsonl` event with the quota units in
metadata, so `costs show` and anomaly detection see volume even at $0 marginal
cost. The cost ledger stays the single record of every spend source.

## Auto-routing requires intent and quota evidence

Vendor CLI execution commands generally do not expose trustworthy *remaining*
quota, so Deepr never auto-routes on a guess. An explicit, dated admission is
still useful, but it records operator intent only. It does not replace the
remaining-quota gate:

- `deepr capacity admit-plan codex --task-class sync` (and `revoke-plan`) records
  a plan admission in the shared admission store, namespaced `plan:<id>` so the
  local rung never mistakes it for an Ollama model. Only the genuinely
  free-at-margin, ToS-clean backends (codex/claude/opencode) can be admitted.

The waterfall's plan-quota rung (`choose_maintenance_backend` ->
`_choose_plan_quota`) auto-selects a CLI only when it is installed, in plan auth
mode, admitted for the task class, **and has a trusted remaining-quota
observation** in the local quota ledger. A backend seen `EXHAUSTED` with a
future `reset_at` is skipped. Once the reset passes, the exhaustion no longer
blocks it, but a fresh trusted remaining-quota observation is still required
before auto-routing resumes. Metered stays the budget-gated last resort.

The explicit path needs no admission (the operator chose it directly):

- `deepr expert sync NAME --plan codex` (also `absorb`, topic `learn`, `learn-web`,
  `route-gaps --execute`).
- `deepr capacity probe-plan codex` - validate auth + one round-trip.
- `deepr capacity probe-fleet --backend codex --backend claude` - validate
  several selected backends concurrently, record the same usage/exhaustion
  observations as `probe-plan`, and emit a versioned
  `deepr-plan-fleet-probe-v1` payload. This is validation fan-out, not
  auto-routing permission.
- `deepr capacity validate-fleet --backend codex --backend claude` - run the
  transport probe and no-metered consult contract as one operator health check,
  emit `deepr-plan-fleet-validation-v1`, and fail selected backends that are
  skipped, missing, exhausted, timed out, or return failed synthesis status.
  This is still validation fan-out, not auto-routing permission or semantic
  answer scoring.
- `deepr mcp validate-consult-fleet --plan codex --plan claude` - run the
  no-metered consult contract through selected plan CLIs concurrently and emit
  `deepr-mcp-consult-fleet-validation-v1`. This proves consult envelope,
  capacity, trace, cost, and collaboration metadata across multiple backends;
  it still does not score answer meaning.

`choose_plan_quota_backend` resolves an explicit `--plan` request through the
same safety gate but without the admission/observed-quota requirement.

## Fleet visibility

`deepr capacity fleet` (builder: `fleet.build_fleet_status`) shows every
plan-quota CLI in one read-only `$0` table: installed (PATH), effective child
auth mode after metered env vars are removed, raw parent-shell auth mode for
diagnostics, routability (auto / explicit / metered), and the latest *observed*
quota state (active / exhausted / quarantined / unobserved) with a reset time
when one was parsed from the vendor's exhaustion message or from a metadata
refresh. "unobserved" and a blank reset are deliberate: Deepr reports only what
it has seen, never a fabricated remaining-quota number. Reset times are recorded
on `EXHAUSTED` events by `parse_reset_after_seconds`, which extracts a relative
duration ("Try again in 3h 42m", "Resets in 2h15m30s") - deterministic *form*
extraction, never a semantic verdict; monthly pools with no countdown stay
honestly unknown. Codex supports proactive metadata refresh:
`deepr capacity refresh-quota codex` reads local session-log `rate_limits`.
Claude Code supports
`deepr capacity refresh-quota claude`, which reads the current user's Claude
Code OAuth usage metadata from the read-only usage endpoint when credentials
are present. Grok supports `deepr capacity refresh-quota grok`, which reads the
current user's Grok CLI auth file and calls the Grok billing metadata endpoint
to parse a monthly gRPC-web quota frame. These refreshes normalize the binding
window through `QuotaSnapshot` and write `VENDOR_REPORTED` ledger events
without running a model call. Published as the versioned
`deepr-plan-fleet-v1` envelope.

`deepr capacity probe-fleet` is the active validation surface: it makes tiny
parallel `Reply with exactly: OK` calls to selected plan CLIs, skips
metered-at-margin adapters unless `--include-metered -y` is set, records
quota-ledger observations, and fails if selected non-skipped backends fail or
nothing actually ran. It is intentionally separate from auto-routing because
most CLIs still do not expose trusted remaining quota.

`deepr capacity validate-fleet` is the defensive operator validation surface:
it runs the transport probe first, then consult-contract validation only for
backends whose transport succeeded. Its wrapper timeout is longer than the
plan-subprocess timeout so typed backend failures can surface, and its report
keeps transport status, consult status, synthesis status, skipped backends, and
failed backends separate.

`deepr mcp validate-consult-fleet` is the contract validation companion. It
fans out in-process `deepr_consult_experts` calls over selected plan backends,
preserves the no-metered fallback invariant, and reports one result per plan.
It is intentionally side-effect and form validation, not a semantic ranking of
which CLI answered best.

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

- Live quota probes that record a *trusted remaining* signal let the
  auto-routing rung light up only when the candidate backend has observed
  headroom. The shared snapshot contract exists, and Codex, Claude Code, and
  Grok now write `VENDOR_REPORTED` ledger events from metadata-only
  refreshes. Next probe: Antigravity as explicit-only metadata visibility.
- `deepr capacity` detection ids are exe-based (`kiro-cli`, `agy`) while
  execution ids are canonical (`kiro`, `antigravity`); the capacity quota display
  for those two does not yet join to execution-recorded usage. Cosmetic.
- Prompt delivery is now per-adapter: `prompt_is_file` (Grok `--prompt-file`),
  `stdin_prompt` (Codex `codex exec -`, Claude `claude -p -`), or a plain argv
  (short-prompt CLIs). `client._build_invocation` resolves the mode, writes a
  temp file for file-mode and removes it after the run, and both `_run_chat` and
  the probe share it. Validated headless on a Windows build 2026-06-25: Codex,
  Claude, and Grok all run end to end with long research/synthesis prompts (Grok
  previously failed with WinError 206 - the prompt exceeded the command-line
  length limit - until it was moved to `--prompt-file`).
- Antigravity drops stdout under a non-TTY pipe (confirmed v1.0.12: `agy -p`
  exits 0 with empty stdout when piped); the fix is not a flag. It now works
  headless by recovering the answer from antigravity's own transcript
  (`~/.gemini/antigravity-cli/brain/<conv-id>/.system_generated/logs/transcript.jsonl`):
  each line is a JSON record, and the reply is the last `PLANNER_RESPONSE`
  record's `content`. `antigravity_transcript.recover_answer` reads the newest
  transcript touched at or after the run start; the adapter sets
  `answer_from_transcript=True` and the client uses it instead of stdout.
  Validated end to end 2026-06-25: `probe_plan_quota(antigravity)` returned the
  expected reply in ~5.5s on plan auth. Antigravity stays explicit-only and ToS
  gray-zone (active ban wave) despite working. Grok also runs but stays
  explicit-only and gray-zone. A ConPTY wrapper remains a possible alternative if
  the transcript path ever changes.
- OpenCode is BYO-provider: today the safety gate treats it as plan-clean, but a
  per-run check of the resolved provider's `auth.json` `type` (oauth vs api)
  would make "don't bill a metered provider" enforcement exact.
