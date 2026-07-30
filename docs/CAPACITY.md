# Capacity and No-Surprise Bills

Deepr has three capacity rungs:

1. Local hardware through Ollama.
2. Explicit non-metered plan-quota CLIs the operator already pays for.
3. Metered provider API previews and accounting, with production dispatch blocked.

The routing principle is cheapest capable path first, but only when the path is
honest. Local capacity can be `$0` at the margin. Plan capacity can be `$0`
inside Deepr but may consume a subscription quota, monthly credit pool, or
external credits. Metered APIs cost money and must be estimated, reserved, and
settled through the canonical ledger.

Metered APIs are explicit premium paths, not an automatic fallback in v2.40. Feature
surfaces that can trigger a distinct paid class, such as image generation, must
not infer paid execution from a text-model API key alone. Portrait generation
auto-selects only a local image endpoint. Paid portrait providers are recognized
but gated before provider construction until they use the shared durable call
transaction. Existing portraits are skipped unless the caller explicitly
forces local regeneration. Generated portraits live under the configured
runtime data root, and forced regeneration archives the previous image before
replacement.

API-backed expert profile setup is gated in v2.40 because hosted storage and
nested learning calls do not yet share one durable parent reservation. Local
profile creation through `deepr expert make --local` stays provider-free.

## Current Status

| Source | Works now | Guardrail |
|---|---|---|
| Local Ollama | `expert make --local`, `expert absorb --local`, `expert sync --local`, `expert sync --local --fresh-context`, `expert sync --local --deep-context`, experimental `expert investigate`, `eval local`, `eval local-context`, and scored admission | No provider API key required; investigation pins native per-request context, requires exact `$0`, and has no fallback; automatic routing requires measured local quality evidence |
| Provider APIs | Write-free request preview and offline billing reconciliation for supported finite provider/model/tool envelopes | Production dispatch is blocked until a provider-specific authenticated account-control verifier and current credential-identity resolver are installed; no automatic paid fallback, hosted storage, standalone metered chat, or unsafe lifecycle dispatch |
| Plan-quota CLIs | Explicit `expert sync --plan <id>`, `expert sync-all --plan <id>`, `expert route-gaps --execute --plan <id>`, `expert absorb --plan <id>`, `expert learn --plan <id>`, `expert learn-web --plan <id>`, `expert consult --plan <id>`, and `capacity probe-plan <id>` for safety-eligible non-metered adapters | Claude Code is currently executable only after a live provider proof that paid extra usage is disabled. Codex, OpenCode, Kiro, Grok, Antigravity, and Copilot remain visible but execution-blocked for the reasons below. API-key env vars are stripped, auth, tool, and overage posture are checked, and automatic routing also requires trusted remaining-quota evidence. |
| CLI judges | Local-eval CLI judge flags remain visible for compatibility; consult-quality judging still has separate explicit local Ollama or safety-eligible `--plan <id>` paths | `--judge-cli`, `--judge-command`, and legacy `--allow-cli-judge` never start a local-eval vendor process because Deepr cannot prove its billing source, paid-overage posture, or total cost. The allow flag is not spend authority. API consult-quality judging shares the blocked provider-account authority gate. |

Expert consult synthesis already supports local and explicit plan capacity.
Experimental `expert investigate` is narrower: it accepts only local Ollama
plans with `--budget-usd 0`, pins the exact expert and review models plus native
context windows, and refuses plan-quota or API execution before dispatch. Its
one parent envelope includes every roster generation, checker, synthesizer,
learning, retrieval, token, time, disk, and cost allowance. A plan preview does
not contact Ollama, so model installation and hardware fit are execution-time
facts. Plan-quota investigation remains a later explicit-only stage, and the
future API form must enforce one total `$5` maximum across all children rather
than treating the budget as per expert.

MCP `deepr_query_expert backend=local|plan` now runs one read-only
compiled-context turn through owned-capacity chat backends with live metered
fallback disabled. MCP `deepr_query_expert backend=api` and every standalone
metered chat path fail closed in v2.40. Full interactive `expert chat` still
needs the shared per-call transaction before it can honestly claim local, plan,
tool, streaming, and paid API parity. The implementation plan is
[expert-chat-capacity-backends.md](design/expert-chat-capacity-backends.md).

Automatic plan routing is not a blanket claim. Claude Code is the only current
auto-routable adapter, and only after a trusted quota observation. Every actual
Claude call repeats a live paid-overage check before the vendor process starts.
Codex, OpenCode, Kiro, Grok, Antigravity, and Copilot remain fleet-visible but
fail before a vendor process starts.

| Adapter | Current execution posture | Why |
|---|---|---|
| Claude Code | Executable; eligible for observed-quota auto-routing | Stored plan auth is classifiable. Every dispatch requires provider metadata proving paid extra usage is off, then uses safe mode with empty tool and MCP surfaces, no persistence, the included `sonnet` alias, and no API credential. |
| Antigravity | Visible/read-only | Native tool permissions and transcript side effects cannot be disabled or confined for untrusted prompts; headless use is also ToS-gray. |
| Codex | Visible/read-only | Its current non-interactive sandbox does not disable or narrowly confine native shell and file reads for untrusted prompts. |
| OpenCode | Visible/read-only | The selected provider, stored credential type, marginal cost, and native tool posture cannot be proven before dispatch. |
| Kiro | Visible/read-only | Read tools are not narrowly confined, and prepaid auth plus overage state cannot be proven before dispatch. |
| Grok Build | Visible/read-only | Native tool permissions cannot be disabled or confined for an untrusted prompt. |
| GitHub Copilot | Visible/read-only | It is metered at the margin and lacks Deepr's complete estimate, reserve, settle, and ledger contract. |

## Operator Commands

```bash
# Setup and visibility.
deepr init --yes --budget 5 --data-dir ~/OneDrive/deepr
deepr doctor --skip-connectivity
deepr capacity
deepr capacity --probe
deepr capacity fleet

# Quota metadata refreshes. These record quota observations, not model calls.
deepr capacity refresh-quota codex
deepr capacity refresh-quota claude
deepr capacity refresh-quota grok

# Read-only route guidance for the next safe action.
deepr capacity next --task-class sync
deepr capacity next --task-class sync --context-mode fresh --scheduled
deepr capacity next --task-class sync --context-mode deep --expert "Platform Team Expert"

# Read the spend decisions made by value gates.
deepr costs spend-decisions
deepr costs spend-decisions --expert "Platform Team Expert" --decision deferred
deepr costs spend-decisions --json

# Read strict spend truth and current authority. These make no provider call.
deepr budget status
deepr budget history --limit 20
deepr budget safety
deepr costs show
deepr costs alerts
deepr costs limits
deepr costs doctor --json
```

The OneDrive example relocates expert, report, and `DEEPR_DATA_DIR` runtime
state for sequential device use. It does not enable concurrent writers: stop
Deepr services, finish mutations, and wait for file synchronization before
switching devices. Credentials remain local. Cost and device-capacity ledgers
should remain machine-specific through their dedicated root overrides, while
queues, traces, benchmarks, observability artifacts, and several MCP databases
follow a synced `DEEPR_DATA_DIR` today.

`deepr capacity next` runs no research and makes no provider generation call. It
explains whether a job can use local capacity and whether the local model lacks
admission evidence. It never evaluates plan eligibility or proposes a metered
expert-lifecycle fallback. Use `capacity fleet` for registered plan adapters;
an optional API action is only a no-spend preview of a separate research job.

Base `deepr capacity` is inventory only. Its human labels mean local runtime
detected, plan CLI installed, or API credential configured. Compatibility JSON
retains `available` but adds `availability_basis`, null
`execution_eligible` for present but unresolved sources, and false
`execution_eligible` for absent sources. Local and registered plan-adapter
entries name their next inspection command; unadapted plan-style CLIs and API
entries leave it null. An exact API query is required. Use `capacity fleet`
for registered plan-adapter blockers. See
[Workflow Readiness Language](design/workflow-readiness-language.md).

## Local Capacity

Local models do not browse on their own. Freshness comes from a source pack
created before the local model call.

```bash
deepr expert make "Platform Team Expert" --local -d "Platform engineering knowledge"
deepr expert absorb "Platform Team Expert" report.md --local
deepr expert sync "Platform Team Expert" --local
deepr expert sync "Platform Team Expert" --local --fresh-context
deepr expert sync "Platform Team Expert" --local --deep-context
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims --stage-compiled-claims
```

`--fresh-context` builds a small free-only retrieval pack. `--deep-context`
builds a bounded multi-query retrieval pack. These paths can fetch explicit
URLs or use direct DuckDuckGo when the optional `ddgs` dependency is installed.
`DEEPR_SEARXNG_URL` remains configuration-readable, but Deepr does not dispatch
to it because a loopback or self-hosted label cannot prove that its upstream
engines have zero marginal cost. They do not use Brave, Tavily, or other
API-key search backends. Before any local or plan model dispatch,
search-discovered fresh context must contain at least two content-addressed
sources, deep context must contain at least three, and an explicit-URL request
must contain at least one. Under-ready packs are still persisted for diagnosis,
then return a retryable no-metered failure without a model/plan call or cadence
advance instead of absorbing uncertainty as permanent beliefs.

Context-bearing sync runs write a source-pack artifact and deterministic
compiler artifacts under the expert knowledge directory:

```text
sync_artifacts/source_packs/<timestamp>_<topic>.json
sync_artifacts/source_pack_manifests/<timestamp>_<topic>.json
sync_artifacts/source_notes/<timestamp>_<topic>.json
sync_artifacts/claim_extractions/<timestamp>_<topic>.json
sync_artifacts/claim_verifications/<timestamp>_<topic>.json
sync_artifacts/graph_commit_envelopes/<timestamp>_<topic>.json
sync_artifacts/graph_commit_apply_results/<timestamp>_<topic>.json
```

The manifest and source notes record provenance shape, excerpt hashes,
content-hash validity, source windows, and readiness for semantic compile. They
make no model calls and emit no semantic verdicts. `--compile-claims` adds
explicit sidecar model calls over ready source-note windows, writes
`deepr-semantic-claim-extraction-v1` candidates, runs budget-gated claim
verification with read-only recall context, builds a graph-commit envelope,
applies that verified envelope instead of the legacy absorber, and writes a
graph-commit apply result sidecar. Verifier-supplied edge decisions can carry
structured temporal qualifiers into the envelope and persisted edge. Use
`--stage-compiled-claims` with `--compile-claims` to keep graph writes disabled
and persist only the compiler sidecars. `--apply-compiled-claims` remains a
compatibility alias for the default compiled apply behavior and is rejected with
`--dry-run`.
On local capacity they cost `$0`;
on non-metered plan capacity they cost `$0` inside Deepr but consume
subscription quota. A metered-at-margin plan CLI remains visible but cannot
dispatch until its adapter has deterministic estimation, durable reservation,
usage settlement, and canonical cost-ledger support. Confirmation flags cannot
override that boundary. Metered API compiled sync is gated in v2.36 until every
nested call uses the shared durable transaction. If the source pack cannot
be persisted, Deepr
fails closed and does not absorb the context-grounded answer.

## Local Admission

Free does not outrank quality. Automatic local routing requires a measured
admission score.

```bash
deepr eval local --model qwen2.5:14b --judge-model qwen2.5:14b --save
deepr eval local-context --model qwen2.5:14b --judge-model qwen2.5:14b --save
deepr capacity admit --from-eval latest --task-class sync --yes
deepr capacity admissions
deepr capacity revoke qwen2.5:14b --task-class sync
```

Admissions are machine-local because local hardware and local model quality
differ per machine. Use `--local` as an explicit override when you want local
execution even without automatic admission.

## Plan-Quota CLIs

Plan-quota adapters drive a vendor CLI as a subprocess instead of a metered HTTP
API. This is intentionally not a `DeepResearchProvider`: a subprocess CLI has a
different contract.

```bash
deepr capacity probe-plan claude
deepr capacity probe-fleet --backend codex --backend claude --backend grok --backend antigravity --json
deepr capacity validate-fleet --backend claude --expert "AI Agent Harnesses" --json
deepr mcp validate-consult-fleet --plan claude --json
deepr expert sync "Platform Team Expert" --plan claude -y
deepr expert sync-all --plan claude -y
deepr expert absorb "Platform Team Expert" report.md --plan claude -y
deepr expert learn "Platform Team Expert" "new platform engineering signals" --plan claude -y
deepr expert consult "What changed in plan capacity?" --plan claude --json
deepr expert judge-consult-quality "Platform Team Expert" consult_abc123 --plan claude --json
```

Run Claude plan commands from a dedicated shell without `ANTHROPIC_API_KEY`.
For PowerShell, remove it only from that shell with
`Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue`. The stored
Claude subscription login remains intact. Deepr intentionally refuses when the
API credential is present rather than guessing which authentication path the
vendor will charge.

The API judge form is visible but gated in v2.36.

Before launch, Deepr removes known metered API-key environment variables for the
selected adapter and evaluates the sanitized child environment. If the CLI
would authenticate through a metered API key, if stored auth is unclassified,
or if native tools cannot be disabled or narrowly confined, Deepr refuses the
plan path. An explicit flag and a zero-dollar budget do not bypass this gate.

Claude adds a per-dispatch money gate because a subscription account may have
paid extra usage enabled. Deepr reads the same OAuth usage metadata used by the
quota refresh, durably records the observation, and requires `extra_usage` to
explicitly report disabled. Missing credentials, an unavailable endpoint, an
unknown field, enabled extra usage, or a ledger failure all stop before the
model process. The call is pinned to the included `sonnet` alias and runs as:

```text
claude --safe-mode --tools "" --no-session-persistence --disable-slash-commands --strict-mcp-config --mcp-config '{"mcpServers":{}}' --model sonnet -p -
```

This means `--plan-model` currently accepts only `sonnet` for Claude plan
capacity. Another billing class is preview-only while production provider API
dispatch remains quarantined. On Windows, Deepr never executes `.cmd` or `.bat` shims. For the
official Claude npm package it resolves the confined packaged `claude.exe`
directly; an absent, redirected, or non-native package binary fails closed.

Claude Code 2.1.206 rejects `--max-budget-usd 0`; that flag accepts only a
positive value. Deepr does not substitute a positive value because doing so
would describe permission to spend. `--bare` is also unsuitable because it
intentionally disables OAuth and keychain reads. Safe mode preserves plan auth
while disabling customizations; explicit empty tools and strict empty MCP
configuration close the remaining agent surface. The no-bill boundary is the
freshly observed provider-side `extra_usage.is_enabled: false` state plus
refusal of API credentials. If that provider proof cannot be obtained and
durably recorded, the model process does not start.

Metered-at-margin adapters such as Copilot are fleet-visible but not executable
through plan-quota commands. `probe-plan`, `probe-fleet`, sync, and absorb reject
them before probe or client construction because the existing `$0` quota event
cannot truthfully represent per-token spend. The retained Copilot choice,
`--include-metered`, and `-y` flags are compatibility surfaces, not spending
authorization.

Fleet-visible adapters declare bounded prompt delivery modes, even when another
safety decision currently blocks execution:

- Codex uses stdin.
- Claude uses stdin.
- Grok uses a prompt file.
- Antigravity's blocked adapter describes transcript recovery for diagnostics;
  it cannot execute until both native tools and transcript side effects are
  safely confined.

Every plan subprocess also drains stdout and stderr concurrently under an
independent 8 MiB raw-byte ceiling for each stream. Crossing either ceiling
requests bounded process-tree termination and returns `output_limit_exceeded`.
If termination or reaping cannot be confirmed, a typed cleanup error takes
precedence. The
bounded partial output is never used as an answer. Because the vendor may have
consumed quota before overflow, Deepr records unknown quota usage and one paired
`$0` canonical cost event under the same attempt id. It never retries or changes
backend after this dispatched outcome.
On Windows, Deepr assigns the suspended child to a kill-on-close Job Object
before it can run. Linux adds a child-subreaper supervisor so even a detached
session is adopted and terminated. Other POSIX systems fail before launch while
equivalent detached-descendant ownership is unavailable. Job termination or
handle-close failure is a typed cleanup error. Handle close is retried within a
fixed bound, unresolved handles retain a process-global cleanup owner that
blocks later launches, and Windows termination uses only stable process and Job
Object handles rather than a reusable PID. Linux supervisor status uses
a parent-only pipe rather than vendor-controlled output, and failed child
enumeration or forced supervisor termination fails closed. Cleanup never
re-buffers output through `communicate()`, and the elapsed timeout includes
process launch. If launch itself remains pending beyond the cleanup grace period,
the late process stays under a tracked cleanup owner and the caller receives an
explicit cleanup error. Antigravity dispatch and transcript recovery are
serialized across processes and correlated to a unique per-attempt nonce in the
exact post-baseline user prompt. Snapshot scanning runs off the event loop under
the same elapsed deadline. Root entries, changed transcripts, actual bytes read,
decoded answers, and lazy line iteration are bounded to one 8 MiB operation
ceiling. Transcript lock release failures are typed and cannot replace a primary
cancellation or accounted failure.

Quota events go to `data/capacity/quota_ledger.jsonl`. Eligible non-metered
plan calls write the canonical cost ledger as `$0` entries when Deepr itself
made no metered API call.

`deepr capacity probe-fleet` validates plan CLI transport and auth in one
bounded concurrent pass. `deepr capacity validate-fleet` is the operator
end-to-end health check: it runs the transport probe first, records quota
observations, then runs the no-metered consult contract only for backends whose
transport succeeded. It emits `deepr-plan-fleet-validation-v1`, fails selected
backends that are missing, skipped, exhausted, or fail synthesis status, and
keeps live metered fallback disabled. `deepr mcp validate-consult-fleet` is the
lower-level consult-contract companion and emits
`deepr-mcp-consult-fleet-validation-v1`. These commands verify form, capacity,
cost, trace, synthesis status, and collaboration metadata only; answer quality
still belongs to human or calibrated-model review.

## Scheduled Maintenance

Scheduled mode is conservative. It waits instead of spending when cheap capacity
is blocked.

```bash
deepr expert sync "Platform Team Expert" --scheduled --fresh-context -y
deepr expert route-gaps "Platform Team Expert" --execute --scheduled --json
deepr expert reflect "Platform Team Expert" <job_id> --execute-followups --scheduled --json
deepr expert health-check "Platform Team Expert" --scheduled --json
deepr expert health-check "Platform Team Expert" --archive-stale --scheduled --json
deepr expert loop-status "Platform Team Expert" --json
```

Scheduled sync consumes `capacity next` guidance. Scheduled gap-fill,
reflection, and health-check surfaces return wait or action-plan payloads
instead of starting metered work. Rerunning without `--scheduled` or supplying
confirmation does not unlock metered gap-fill or reflection in v2.36. Use an
explicit local or trusted plan path where supported; otherwise wait or stop.
These payloads include durable loop-run records and published schema identifiers.

Scheduled local sync, sync-all, and local route-gaps take one read-only
best-effort GPU occupancy observation before constructing the maintenance
engine. Plan-backed scheduled compiled sync applies the same gate when
`--recall-embedding-model` adds a local Ollama embedding step. A confirmed busy signal
records a per-expert WAITING loop outcome with
`stop_reason=capacity_unavailable`, `capacity_unavailable_reason=local_gpu_busy`,
`retry_after_seconds`, and an absolute UTC `retry_at`. Consecutive busy waits
adapt from 30 minutes to 2 hours to a capped 6 hours. The command does not sleep,
kill another workload, or fall through to plan/API capacity. `nvidia-smi` GPU
utilization is the first supported signal; resident VRAM is deliberately not a
busy verdict because Ollama keeps models loaded. Missing or malformed probe
support reports `unknown` and allows dispatch. `deepr capacity` and
`deepr capacity next` expose the observation. Busy wait artifacts preserve the
requested operation and material options as argument-safe `command_argv`, plus
the selected capacity and model identifiers, so retries retain local/plan,
sync-all, context, compile, and route settings without shell reconstruction.
Explicit local work without `--scheduled` remains an operator override. See
[scheduled-local-capacity.md](design/scheduled-local-capacity.md).

`deepr expert sync-all --scheduled` and scheduled `deepr expert route-gaps
--execute` now use the shared waterfall for non-metered dispatch. `sync-all`
uses the `sync` task class; gap-fill uses the `gap_fill` task class. Both can
consume an admitted plan backend only when a trusted quota observation says
usable headroom remains, and both wait instead of falling through to metered
API work in scheduled mode. `sync-all --plan <id>` and
`route-gaps --execute --plan <id>` are the explicit non-metered plan overrides.

## Cost Accounting Rules

- `deepr budget set N` is the shared UTC-month paid API wallet across CLI,
  web, REST, MCP, scripts, workers, and unrelated commands. A command budget is
  a narrower child envelope, never a separate wallet or permission to exceed N.
- `deepr budget set 0` and `deepr budget freeze --reason TEXT` block new paid
  dispatch. `deepr budget unfreeze` requires fresh content-addressed evidence
  for the current typed freeze and cannot restore exhausted headroom. Evidence
  is authoritative only after a provider-specific authenticated source verifier
  and current account, scope, and credential resolver both succeed.
- Effective per-job, UTC-day, UTC-week, and UTC-month limits are the tightest of
  the operator wallet, `DEEPR_MAX_COST_PER_*`, legacy compatibility caps,
  caller envelopes, and compiled safety ceilings. Missing monthly authority,
  malformed policy, or unreadable cost state fails closed.
- Admission and the immediate pre-dispatch mark both count canonical settled
  spend plus every active durable hold. Lowering a positive cap therefore stops
  old reservations that no longer fit.
- Local Ollama and successful safety-eligible plan-quota services report `$0`
  Deepr dollar cost.
- Every enabled provider API call reserves a complete finite maximum before dispatch.
- Enabled provider API completions settle from provider-reported usage or the
  conservative held maximum when usage is absent or invalid.
- Definite pre-dispatch failures refund reservations. Ambiguous or marked
  post-dispatch failures settle conservatively.
- Cached input, cache creation, cache reads, reasoning tokens, and large-context
  pricing tiers are provider-specific and must be preserved in usage metadata.
- If a provider omits cached-input pricing, Deepr charges cached tokens at the
  normal input rate to avoid undercounting.
- Provider prompt-cache controls remain planned until TTL, cache-key, and
  pre-warm estimators are explicit and budget-gated.
- Value-of-spend gates write their allow/defer decisions to
  `spend_decisions.jsonl` under the cost data root. Inspect them with
  `deepr costs spend-decisions`; this command is read-only and costs `$0`.
- Budget history and current cost views read a strict locked ledger snapshot.
  They report settled spend, durable active holds, exposure, per-window
  remaining capacity, and the maximum new paid call allowed by every cap. If
  either money store is unreadable, authorizable headroom is zero.
- `deepr costs limits --monthly N` updates the binding operator month budget.
  The old dashboard-only daily setter is refused because it never governed
  paid dispatch. Set `DEEPR_MAX_COST_PER_DAY` in the Deepr runtime environment
  and restart the process to change authoritative daily policy.
- Central metered wrappers preserve a client correlation ID, provider HTTP
  request ID when exposed, and a separate provider object ID. These are billing
  join evidence, not proof of the provider invoice.

## Provider Account Controls

Deepr's hard ceiling controls calls admitted through Deepr. It cannot prevent a
manual provider call, another application using the same credential, a leaked
credential, a provider pricing defect, delayed billing, or invoice tax. Treat
provider-side controls as an independent boundary.

For each paid API account or project, record each control as one of:

- `verified by Deepr`: current authoritative evidence was read and bound to the
  exact account or project.
- `operator-attested`: the operator confirmed the setting, but Deepr cannot
  verify it.
- `unknown`: no usable evidence exists. Unknown never authorizes more spend.

The minimum account checklist is:

1. A dedicated project or billing scope for Deepr, not a shared general key.
2. The smallest available provider hard limit, prepaid balance, or disabled
   paid-overage setting. A soft alert is not a hard limit.
3. Alerts at 50, 80, 95, and 100 percent delivered to a monitored destination.
4. A non-secret account, project, workspace, and key fingerprint recorded for
   invoice joining. Never store the credential value in cost metadata.
5. Regular read-only billing exports containing UTC period, currency, request
   or job IDs, exact model and tier, token, tool, cache, storage, and other
   billed units, actual charge, credits, adjustments, and tax.
6. A freeze and credential-rotation procedure for any unexplained positive
   invoice drift.

`deepr costs reconcile-billing FILE` now previews a bounded normalized provider
statement offline without writing files. `--apply` stores sanitized,
content-addressed evidence and freezes paid work on incomplete, ambiguous,
unknown, provisional, unsupported, or positively divergent results. Capacity
classes are explicit, and only `api_metered` lines can receipt-match paid ledger
events. A clean result never unfreezes paid work.

Provider-specific authenticated hard-limit verification is not shipped in
v2.40.0. Locally constructed account-control JSON, a posture label, and a local
hash are not proof. Production paid dispatch therefore remains blocked until an
authenticated provider adapter can verify the source and bind the exact active
account, scope, credential fingerprint, owned client, official endpoint, and
canonical outbound model. The provider hard no-overage ceiling must be no
higher than the operator ceiling and must be observed live for each one-use
dispatch. Keep provider-side controls active and reconcile any unexplained
charge before enabling such an adapter.

## Costing Deep Dive

Current provider APIs make cost accounting a multi-bucket problem. Deepr's
budget gates must stay conservative until each enabled path can estimate,
reserve, settle, and audit every bucket it can trigger.

- Token usage is not only input plus output. Preserve cached input, cache
  creation, cache reads, reasoning or thinking tokens, tool-use tokens,
  multimodal tokens, and large-context tier metadata when the provider exposes
  them.
- Provider-returned exact cost wins at settlement when present. xAI, for
  example, returns per-request `cost_in_usd_ticks` that already includes token
  cost, prompt-cache discounts, and server-side tool invocation cost.
- Server-side tools can be separate spend sources. Web search, X search, code
  execution, file or collection search, grounding, and remote tool calls must
  have explicit preflight estimates and settlement paths before automatic use.
  xAI documents that one agent turn may invoke multiple tools in parallel, so
  `max_turns` is not a hard tool-invocation or dollar ceiling. Deepr keeps that
  legacy metered search path gated until the total tool bill is bounded.
- OpenAI Code Interpreter is memory-tiered and billed per 20-minute session.
  Deepr blocks it before dispatch until memory, session count, duration, and
  reuse fit the same reservation. Provider webhooks and retained response
  context are also blocked because they can trigger separately billed work or
  hidden input outside the admitted envelope.
- Batch, flex, priority, provisioned, data-residency, and deployment-tier
  modifiers must be modeled as first-class pricing dimensions, not hidden in a
  single model price.
- Anthropic Claude Sonnet 5 and Opus 4.8 must use the native Messages API
  adapter. Sonnet 5 has a 1M context window and 128K max output, rejects
  non-default sampling params such as `temperature`, `top_p`, and `top_k`, and
  uses adaptive thinking by default; manual thinking budgets are rejected on the
  adaptive-only Claude models. Deepr estimates Sonnet 5 with the standard
  post-intro token rates rather than Anthropic's lower 2026-06 introductory
  rates, so budget gates remain conservative after the intro window.
- Provider cache semantics differ. OpenAI, Azure OpenAI, and Gemini can apply
  implicit prompt caching; Anthropic exposes explicit and automatic
  `cache_control`; Gemini Interactions currently documents implicit caching
  only. A cache feature for one provider cannot be assumed valid for another.
- Cache controls are not automatically cheaper. Before Deepr adds explicit
  cache controls, it must model minimum token thresholds, TTL, cache-key
  granularity, retention policy, cache write and read rates, pre-warm calls,
  cache misses, overflow behavior, and privacy or data-residency implications.
- Free, local, and plan-quota paths still write `$0` Deepr cost events when
  Deepr made no metered API call. They may still consume local electricity,
  subscription quota, monthly credits, or vendor account balance that Deepr
  cannot prove. Those paths stay explicit or evidence-gated.

Research references used for this policy: [OpenAI prompt caching](https://platform.openai.com/docs/guides/prompt-caching),
[Anthropic prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching),
[Gemini context caching](https://ai.google.dev/gemini-api/docs/caching),
[Gemini token counting](https://ai.google.dev/gemini-api/docs/tokens),
[xAI pricing](https://docs.x.ai/developers/pricing),
[xAI cost tracking](https://docs.x.ai/developers/cost-tracking), and
[Azure OpenAI prompt caching](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching).

## Agentic Balance

Capacity is a workflow boundary. Deterministic code owns spend, quota, auth
mode, child process isolation, timeout, cost settlement, and ledger writes. The
model or CLI owns the generated answer, which must still pass the same
extraction, grounding, contradiction, dedup, and trust-floor gates as any other
source.

Automatic plan dispatch requires observed remaining capacity. Deepr does not
infer free headroom from an installed CLI.

See [plans/AGENTIC_BALANCE.md](plans/AGENTIC_BALANCE.md),
[design/capacity-waterfall.md](design/capacity-waterfall.md), and
[design/plan-quota-cli-backends.md](design/plan-quota-cli-backends.md).
