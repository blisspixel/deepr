# Mixture of Experts and Deepr experts

Status: research note, 2026-09-15. Not shipped capability. Parallel research
may prepare fixtures; it may not widen consult routing, learning policy, or
capacity classes ahead of [v2.51](../../ROADMAP.md#active-release-plan).

## The naming trap

Three different objects share the word "expert":

| Object | What it is | Routing unit | Persistence |
| --- | --- | --- | --- |
| Neural MoE (Switch, Mixtral, DeepSeek-MoE, Grok-1) | A feed-forward subnetwork inside one model | Token | Weights |
| Mixture of Agents (MoA) | Several full models plus an aggregator | Whole prompt | Ephemeral text |
| Deepr expert | Durable epistemic state: beliefs, citations, gaps, briefs, spend posture | Whole question, then a stored packet | Files under the expert root |

They are not the same thing. Mixtral's experts often do not specialize by human
domain. Deepr experts must. A Deepr council is closer to MoA in *workflow shape*
(several specialists, one synthesis) except the specialists are **stored
packets**, not extra model generations. Shipped consult makes zero
expert-generation calls and at most one synthesis call.

**One-line contract:** neural MoE is how a model sparsifies compute. Deepr is
how an operator sparsifies durable expertise. Use the first as a local backend
and as a source of failure-mode names. Do not make it the product ontology.

## What already maps

Deepr already does sparse activation at the fleet layer:

- Keyword-overlap top-k selection, default 3, hard cap
  `MAX_ROUTED_EXPERTS = 10` (`src/deepr/experts/expert_routing.py`).
- Inner packet slice per selected expert (`src/deepr/experts/council.py`).
- Shared kernel (ledger, schemas, consult contract, one synthesis client)
  plus specialist files. That is the DeepSeek shared-FFN analog, not N
  processes.
- `deepr route explain` is a `$0`, no-model, inspectable gate. Neural MoE
  gates are opaque.
- Activating the whole roster is already illegal. Forty-nine experts per
  query would be a protocol break, not a quality upgrade.

The overlap router is high-recall selection, never a verdict
([AGENTIC_BALANCE](../plans/AGENTIC_BALANCE.md)). Flagship tier is
presentation, not a routing prior.

## Failure modes worth stealing (diagnosis, not the loss)

- **Expert collapse.** A few name-overlapping experts absorb auto-consults;
  others never fire. Switch Transformer needed an auxiliary load-balancing
  term for the same reason. Deepr should *measure* collapse, not force
  uniform airtime (that is the too-large-alpha mistake).
- **Zero-overlap recency fallback.** If nobody overlaps, `list_all()` order
  (newest first) becomes the council. That is silent collapse onto whoever
  was touched last.
- **Perspective collapse.** Similarity top-k produces five clones of one
  domain. [Diverse councils](diverse-expert-council.md) already name this.
  It is not a FLOPs problem.
- **Dead experts.** Never routed, never maintained, or selected with an
  empty packet. Analog of unused MoE shards that never learn.
- **Noisy gate.** Word overlap on `security` or `agent` looks sharp and is
  still only recall.

Do not import an auxiliary loss that rewrites selection. Do not train a
neural gate over Deepr experts. That would be an unverified improvement
loop on the wrong object.

## Two useful later increments (behind v2.51)

### 1. Sparse fleet collapse telemetry (`$0`)

User-felt: operators cannot see whether the library has collapsed to two
name-overlapping experts.

Exit gate: a write-free report over `selection_mode == "automatic"` consult
traces: selection frequency, unique/N, entropy, top-3 share, recency-fallback
rate. Persist overlap scores and matched terms on the consult trace so "why
this k" is replayable. Join `roster_tier` as a label, never as a prior. No
quality verdict. No routing-default change.

### 2. Local MoE as fit and task annotation, not a capacity class

User-felt: a 24 GB box can run 30B-A3B-class quality at small-model speed
because only a slice of weights fires. An 80B coder MoE (`qwen3-coder-next`)
was already used for `$0` admission. That does not make MoE a fourth
capacity rung.

Keep MoE under owned local Ollama. Implement the staged policy in
[local-model-selection.md](local-model-selection.md): env override, then
admitted+available, then task-class preference. Use measured `weight_bytes`
for fit, not total parameter count. Exclude `*-coder*` (including
`qwen3-coder-next`) from entailment/verification defaults. Keep thinking
disabled on local generation. Keep local MoE tool-free. A missing fit fails
with a pull command, not a paid dense fallback.

## Explicit refusals

- Do not rebrand the expert fleet or council as MoE.
- Do not train a neural router over Deepr experts, or route beliefs per token.
- Do not treat keyword overlap, embeddings, or flagship as authority.
- Do not activate every expert on every query, or force uniform consult load.
- Do not give each expert its own process, tools, filesystem, or subagents.
- Do not add a `local-moe` capacity class. Cost and authority stay the
  existing local rung.
- Do not change consult routing defaults or learning policy before v2.51
  produces usable evidence.
