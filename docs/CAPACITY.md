# Capacity and No-Surprise Bills

Deepr has three capacity rungs:

1. Local hardware through Ollama.
2. Explicit plan-quota CLIs the operator already pays for.
3. Metered provider APIs with budget ceilings.

The routing principle is cheapest capable path first, but only when the path is
honest. Local capacity can be `$0` at the margin. Plan capacity can be `$0`
inside Deepr but may consume a subscription quota, monthly credit pool, or
external credits. Metered APIs cost money and must be estimated, reserved, and
settled through the canonical ledger.

## Current Status

| Source | Works now | Guardrail |
|---|---|---|
| Local Ollama | `expert make --local`, `expert absorb --local`, `expert sync --local`, `expert sync --local --fresh-context`, `expert sync --local --deep-context`, `eval local`, `eval local-context`, and scored admission | No provider API key required; automatic routing requires measured local quality evidence |
| Provider APIs | Full research and high-quality synthesis when keys are configured | Budget ceilings, preflight estimates, reservations, append-only cost settlement |
| Plan-quota CLIs | Explicit `expert sync --plan <id>`, `expert absorb --plan <id>`, `expert learn --plan <id>`, `expert learn-web --plan <id>`, `expert consult --plan <id>`, and `capacity probe-plan <id>` | Metered API-key env vars are stripped from child processes, auth mode is checked, and automatic routing waits for trusted remaining-quota evidence |
| CLI judges | Explicit local eval judging with `--allow-cli-judge` | Opt-in only because Deepr cannot prove whether a vendor CLI uses quota, credits, or metered credentials |

Automatic plan routing is not a blanket claim. Codex, Claude Code, and Grok
have metadata probes. Antigravity and other sources remain explicit-only or
planned until a trustworthy probe and safety gate exist.

## Operator Commands

```bash
# Setup and visibility.
deepr init --yes --budget 5 --data-dir ~/OneDrive/deepr
deepr doctor
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
```

`deepr capacity next` runs no research and makes no provider generation call. It
explains whether a job can use local capacity, whether the local model lacks
admission evidence, whether a plan quota is observed, or whether the operator
must choose an explicitly metered path.

## Local Capacity

Local models do not browse on their own. Freshness comes from a source pack
created before the local model call.

```bash
deepr expert make "Platform Team Expert" --local -d "Platform engineering knowledge"
deepr expert absorb "Platform Team Expert" report.md --local
deepr expert sync "Platform Team Expert" --local
deepr expert sync "Platform Team Expert" --local --fresh-context
deepr expert sync "Platform Team Expert" --local --deep-context
```

`--fresh-context` builds a small free-only retrieval pack. `--deep-context`
builds a bounded multi-query retrieval pack. These paths can fetch explicit
URLs, use configured SearXNG through `DEEPR_SEARXNG_URL`, or use DuckDuckGo
when the optional `ddgs` dependency is installed. They do not use Brave, Tavily,
or other API-key search backends. If no fresh sources are retrieved, Deepr
records no changes instead of absorbing uncertainty as permanent beliefs.

Context-bearing sync runs write a source-pack artifact and deterministic
compiler manifest under the expert knowledge directory:

```text
sync_artifacts/source_packs/<timestamp>_<topic>.json
sync_artifacts/source_pack_manifests/<timestamp>_<topic>.json
```

The manifest records provenance shape, excerpt hashes, content-hash validity,
and readiness for a later semantic compile. It makes no model calls and emits no
semantic verdicts. If the source pack cannot be persisted, Deepr fails closed
and does not absorb the context-grounded answer.

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
deepr capacity probe-plan codex
deepr expert sync "Platform Team Expert" --plan codex -y
deepr expert absorb "Platform Team Expert" report.md --plan claude -y
deepr expert learn "Platform Team Expert" "new platform engineering signals" --plan codex -y
deepr expert consult "What changed in plan capacity?" --plan grok --json
```

Before launch, Deepr removes known metered API-key environment variables for the
selected adapter and evaluates the sanitized child environment. If the CLI would
authenticate through a metered API key, Deepr refuses the plan path. This lets a
normal API-capable shell still run explicit plan commands without surprise
bills.

Long prompts go through safe delivery modes:

- Codex uses stdin.
- Claude uses stdin.
- Grok uses a prompt file.
- Antigravity recovers the answer from its transcript when stdout is empty.

Quota events go to `data/capacity/quota_ledger.jsonl`. Dollar-cost events still
write the canonical cost ledger as `$0` entries when Deepr itself made no
metered API call.

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

Scheduled sync consumes `capacity next` guidance. Scheduled gap-fill, reflect,
and health-check surfaces return wait or action-plan payloads instead of
starting metered work unless the operator deliberately reruns without
`--scheduled` or supplies the required confirmation. These payloads include
durable loop-run records and published schema identifiers.

## Cost Accounting Rules

- Local Ollama and explicit plan-quota services report `$0` Deepr dollar cost.
- Provider API calls reserve estimated cost before dispatch.
- Provider API completions settle from provider-reported usage.
- Submit failures refund reservations.
- Cached input, cache creation, cache reads, reasoning tokens, and large-context
  pricing tiers are provider-specific and must be preserved in usage metadata.
- If a provider omits cached-input pricing, Deepr charges cached tokens at the
  normal input rate to avoid undercounting.
- Provider prompt-cache controls remain planned until TTL, cache-key, and
  pre-warm estimators are explicit and budget-gated.

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
- Batch, flex, priority, provisioned, data-residency, and deployment-tier
  modifiers must be modeled as first-class pricing dimensions, not hidden in a
  single model price.
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
