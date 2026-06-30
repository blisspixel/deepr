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

Metered APIs are the premium fallback, not the default spending path. Feature
surfaces that can trigger a distinct paid class, such as image generation, must
not infer paid execution from a text-model API key alone. Portrait generation
auto-selects only a local image endpoint unless the operator passes an explicit
paid provider or sets the single premium auto opt-in
`DEEPR_ALLOW_METERED_IMAGE_AUTO=1`. Provider-specific image auto env vars are
ignored. It also treats portraits as create-once artifacts by default: existing
portraits are skipped unless the caller explicitly forces regeneration, and
metered web or CLI requests must acknowledge the estimated cost before dispatch.
CLI `--yes` can skip unattended prompts only for free/local image generation unless
`--confirm-metered-cost` is also supplied. Generated portraits live under the
configured runtime data root, and forced regeneration archives the previous
image before replacement.

API-backed expert profile setup is treated the same way. `deepr expert make`
previews the metered provider, file count, upload size, and hosted-vector-store
storage estimate where Deepr has provider-specific pricing before it constructs
a provider client.
Unattended `--yes` runs must also pass `--confirm-metered-profile`. Local
profile creation through `deepr expert make --local` stays provider-free and
does not need that acknowledgement.

## Current Status

| Source | Works now | Guardrail |
|---|---|---|
| Local Ollama | `expert make --local`, `expert absorb --local`, `expert sync --local`, `expert sync --local --fresh-context`, `expert sync --local --deep-context`, `eval local`, `eval local-context`, and scored admission | No provider API key required; automatic routing requires measured local quality evidence |
| Provider APIs | Full research and high-quality synthesis when keys are configured | Premium fallback behind budget ceilings, preflight estimates, reservations, and append-only cost settlement; API-backed expert profile setup previews provider upload/storage posture before provider dispatch |
| Plan-quota CLIs | Explicit `expert sync --plan <id>`, `expert sync-all --plan <id>`, `expert route-gaps --execute --plan <id>`, `expert absorb --plan <id>`, `expert learn --plan <id>`, `expert learn-web --plan <id>`, `expert consult --plan <id>`, and `capacity probe-plan <id>` | Metered API-key env vars are stripped from child processes, auth mode is checked, metered-at-margin CLI backends are rejected for roster plan dispatch, and automatic routing waits for trusted remaining-quota evidence |
| CLI judges | Explicit local eval judging with `--allow-cli-judge`; consult-quality judging through explicit local Ollama, `--plan <id>`, or `--api-provider` | Opt-in only because Deepr cannot prove whether a vendor CLI uses quota, credits, or metered credentials; plan consult-quality judges record `$0` Deepr cost metadata and consume subscription quota; API consult-quality judges require a model, positive budget, cost confirmation, preflight reservation, and ledger settlement |

Expert consult synthesis already supports local and explicit plan capacity.
MCP `deepr_query_expert backend=local|plan` now runs one read-only
compiled-context turn through owned-capacity chat backends with live metered
fallback disabled. MCP `deepr_query_expert backend=api provider=anthropic`
now supports explicit non-agentic metered Anthropic chat with native usage
settlement. Full interactive `expert chat` still needs more backend-neutral
work before it can honestly claim local, plan, tool, streaming, and paid API
parity. The implementation plan is
[expert-chat-capacity-backends.md](design/expert-chat-capacity-backends.md).

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
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims --stage-compiled-claims
```

`--fresh-context` builds a small free-only retrieval pack. `--deep-context`
builds a bounded multi-query retrieval pack. These paths can fetch explicit
URLs, use configured SearXNG through `DEEPR_SEARXNG_URL`, or use DuckDuckGo
when the optional `ddgs` dependency is installed. They do not use Brave, Tavily,
or other API-key search backends. If no fresh sources are retrieved, Deepr
records no changes instead of absorbing uncertainty as permanent beliefs.

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
subscription quota. A metered-at-margin plan CLI is explicit-only, shows the run
budget ceiling and known claim-compilation estimate in the confirmation prompt,
and must pass the budget and cost-ledger gate before dispatch. Metered API
capacity uses the same budget and cost-ledger gate. If the source pack cannot
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
deepr capacity probe-plan codex
deepr capacity probe-fleet --backend codex --backend claude --backend grok --backend antigravity --json
deepr capacity validate-fleet --backend codex --backend claude --backend grok --backend antigravity --expert "AI Agent Harnesses" --json
deepr mcp validate-consult-fleet --plan codex --plan claude --plan grok --plan antigravity --json
deepr expert sync "Platform Team Expert" --plan codex -y
deepr expert sync-all --plan codex -y
deepr expert absorb "Platform Team Expert" report.md --plan claude -y
deepr expert learn "Platform Team Expert" "new platform engineering signals" --plan codex -y
deepr expert consult "What changed in plan capacity?" --plan grok --json
deepr expert judge-consult-quality "Platform Team Expert" consult_abc123 --plan codex --plan-model gpt-5-mini --json
deepr expert judge-consult-quality "Platform Team Expert" consult_abc123 --api-provider xai --api-model grok-4.3 --budget 0.50 --confirm-metered-cost --json
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
instead of starting metered work unless the operator deliberately reruns without
`--scheduled` or supplies the required confirmation. These payloads include
durable loop-run records and published schema identifiers.

`deepr expert sync-all --scheduled` and scheduled `deepr expert route-gaps
--execute` now use the shared waterfall for non-metered dispatch. `sync-all`
uses the `sync` task class; gap-fill uses the `gap_fill` task class. Both can
consume an admitted plan backend only when a trusted quota observation says
usable headroom remains, and both wait instead of falling through to metered
API work in scheduled mode. `sync-all --plan <id>` and
`route-gaps --execute --plan <id>` are the explicit non-metered plan overrides.

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
