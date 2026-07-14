# Deepr Threat Model

Status: current with Deepr v2.36.1. Last reviewed: 2026-07-13.

This document is the repository-scoped threat model for Deepr. It is intended
for security reviews, design reviews, and future bug discovery. It should stay
grounded in Deepr's actual product surface rather than generic model-security
concerns.

## Overview

Deepr is a local-first, multi-provider research and expert-memory system. It
routes research and expert-maintenance work through local models, explicit
plan-quota CLIs, or metered provider APIs, then persists reports, expert
profiles, beliefs, gaps, temporal edges, loop records, cost ledgers, MCP/A2A
handoff artifacts, and derived views.

Primary runtime surfaces:

- CLI commands under `src/deepr/cli/`.
- Web dashboard and API routes under `src/deepr/web/` and `src/deepr/api/`.
- MCP stdio and HTTP/SSE server under `src/deepr/mcp/`.
- A2A host-facing task and Agent Card surfaces under `src/deepr/a2a/`.
- Provider adapters under `src/deepr/providers/`.
- Local, plan-quota, and owned-capacity backends under `src/deepr/backends/`.
- Expert state, graph-commit, sync, consult, monitor, and memory-card flows
  under `src/deepr/experts/`.
- Local storage, reports, cost ledgers, quota ledgers, audit logs, schemas, and
  generated artifacts under the configured runtime data root.

The security goal is not to make model output "true" by rule. Deepr's security
goal is to keep attacker-controlled input, model-controlled output, provider
credentials, remote agent calls, local files, durable expert memory, and paid
capacity inside explicit trust boundaries. Deterministic code owns
authentication, authorization, schemas, path safety, rate limits, budget
gates, cost settlement, quota observation, audit logs, idempotency, locks, and
write boundaries. Human or calibrated-model judgment owns semantic meaning:
grounding, contradiction, deduplication, hallucination labels, synthesis
quality, and expert perspective quality.

## Threat Model, Trust Boundaries, and Assumptions

### Assets

Assets and privileges that matter:

- Provider API keys, plan CLI sessions, MCP scoped keys, web API tokens, and
  local environment variables.
- Metered provider budget, daily/monthly limits, prepaid plan quota, local GPU
  time, and any quota-consuming external CLI calls.
- Expert memory: profiles, belief event logs, graph state, temporal edges,
  hypotheses, stances, original ideas, self-model records, consult traces, and
  loop records.
- Source material and generated artifacts: reports, source packs, handoff
  payloads, OKF bundles, memory cards, schema-versioned eval reports, and
  published MCP/A2A outputs.
- Local filesystem paths under the runtime data root and any configured
  reports, experts, documents, logs, or benchmark directories.
- Remote-call audit logs and cost/quota ledgers, which are security evidence as
  well as operational telemetry.
- Host-agent trust: MCP and A2A clients may use Deepr output to decide what to
  do next, so malformed, overbroad, or secret-bearing artifacts can become
  downstream security problems.

### Actors

- **Operator:** the human who installs Deepr, provides provider keys or plan CLI
  sessions, configures budgets, starts local or hosted endpoints, and approves
  paid or write-capable work.
- **Local user:** a user on the same workstation who can invoke the CLI or
  reach loopback services.
- **Remote host agent:** an MCP or A2A client that can read or call Deepr tools
  through stdio, loopback HTTP, or a TLS-proxied endpoint.
- **External content author:** a person or system controlling web pages, search
  snippets, uploaded docs, reports, source packs, prior artifacts, or tool
  outputs that Deepr ingests.
- **Provider or plan backend:** hosted model APIs and CLI tools that produce
  model output and may report usage, errors, quota state, or billing metadata.
- **Malicious reachable peer:** any network actor able to reach a public-bind
  web, MCP, or A2A endpoint.
- **Repository contributor:** a developer or dependency update that can change
  code, schemas, tests, configuration, or docs.

### Trust Boundaries

The main boundaries are:

- **Operator-controlled configuration to runtime behavior.** Environment
  variables, config files, local paths, provider keys, and CLI flags enter
  routing, provider construction, storage roots, and budget limits.
- **Untrusted content to prompts and expert memory.** Web results, scraped
  pages, uploaded docs, previous reports, first-party tool output, MCP tool
  output, and source-pack content are untrusted even when they are useful
  evidence.
- **Model output to durable writes.** Provider and plan outputs may propose
  claims, edges, gaps, hypotheses, stance, or self-model updates. They cannot
  directly mutate canonical memory without schema, verifier, review, budget,
  and apply gates.
- **Local-only surface to reachable network service.** Web, MCP HTTP, and A2A
  endpoints are low risk on loopback and high risk when reachable without
  scoped credentials, budgets, and rate limits.
- **Read-only host access to sensitive or mutating expert tools.** A host that
  can discover or query experts must not automatically gain permission to
  mutate memory, run paid research, execute tools, or read sensitive expert
  state.
- **Free-at-margin capacity to metered spend.** Local Ollama and explicit
  plan-quota capacity may be `$0` inside Deepr but still consume hardware,
  subscription quota, or external credits. API and metered-at-margin paths are
  premium and must remain explicit.
- **Generated artifacts to downstream agent action.** Handoff, OKF, report,
  A2A, and MCP artifacts are derived views. They may inform another agent but
  are not the canonical expert store and must carry schema, trace, cost, and
  provenance metadata.
- **Developer and CI tooling to production guarantees.** Tests, scripts,
  fixtures, docs, and local agent scratch are not production inputs, but they
  must not leak real keys, encourage unsafe commands, or silently rely on live
  provider access.

### Assumptions

- Deepr does not train, fine-tune, serve, or protect model weights. Model
  training-time poisoning, model extraction, membership inference, and serving
  enclave defenses are provider responsibilities.
- The operator controls the machine, the configured provider accounts, and any
  plan CLI credentials. Deepr should warn and gate dangerous use, but it cannot
  prove vendor billing policy beyond observed usage, official metadata, and
  configured auth mode.
- Local filesystem state is trusted only within validated roots. User-supplied
  path segments, artifact IDs, report IDs, expert names, source paths, and URLs
  are attacker-controlled until validated.
- Remote MCP HTTP and A2A use are experimental unless deployed behind HTTPS
  with scoped keys, per-key budgets, rate limits, audit logs, and endpoint
  smoke validation.
- Unit tests must not need provider keys or outbound network access. Live
  integration tests require an explicit opt-in and should never be the default
  developer path.

## Attack Surface, Mitigations, and Attacker Stories

### Ingestion and Prompt-Injection Surface

Attacker-controlled inputs:

- Web search snippets and scraped pages.
- Uploaded local documents and report files.
- Source packs, source-note windows, and source-pack manifests.
- Prior reports, campaign contexts, first-party tool output, and MCP tool
  results.
- Host-supplied consult prompts, expert questions, and A2A task requests.

Relevant attacker stories:

- A malicious web page instructs the model to ignore system instructions,
  reveal secrets, call tools, or write a false belief.
- A source pack embeds tool-call or JSON snippets that look like trusted MCP or
  A2A results.
- A high-authority looking document tries to turn a citation into a durable
  belief without verifier support.
- A host passes a prompt that attempts to coerce an expert into disclosing
  sensitive internal state or remote bearer tokens.

Existing controls:

- `src/deepr/utils/prompt_security.py` wraps and sanitizes untrusted content
  before prompt use.
- Consult-quality and hallucination-risk surfaces treat semantic labels as
  human or calibrated-model review outputs, not deterministic truth.
- Graph commit and sync apply paths use schema-versioned envelopes and
  explicit apply results before durable memory writes.
- Source packs, handoff payloads, consult traces, memory cards, OKF bundles,
  and generated reports are derived views over canonical state, not authority
  by themselves.
- `docs/plans/AGENTIC_BALANCE.md` requires deterministic code to guard
  side effects and model/human judgment to own meaning.

Security invariant:

Untrusted content can influence model judgment inside a bounded prompt, but it
must not by itself authorize spend, reveal credentials, bypass schemas, mutate
expert state, or convince deterministic code that a semantic claim is true.

### MCP, A2A, and Host-Agent Surface

Attacker-controlled inputs:

- MCP JSON-RPC requests, tool names, tool arguments, bearer tokens, scoped key
  values, and HTTP headers.
- A2A Agent Card consumers, task requests, metadata, backend selection, and
  attached artifacts.
- Remote host prompts and result consumers that may treat Deepr output as an
  action plan.

Relevant attacker stories:

- A remote host with read-only expectations calls a mutating tool or a paid API
  tool.
- A public MCP HTTP bind without credentials allows a network peer to read
  expert state or spend provider budget.
- A tool result spoofs another tool's output shape or hides a secret inside a
  returned artifact.
- A host asks for API synthesis while omitting an explicit budget or metered
  approval.

Existing controls:

- `src/deepr/mcp/security/tool_allowlist.py` categorizes tools by read, write,
  execute, and sensitive behavior across `READ_ONLY`, `STANDARD`, `EXTENDED`,
  and `UNRESTRICTED` modes.
- `src/deepr/mcp/security/scoped_keys.py` stores scoped key hashes, supports
  revocation, expert allowlists, per-key budgets, rate limits, argument hashes,
  and remote audit records.
- `src/deepr/mcp/transport/http.py` refuses unauthenticated public binds by
  default, accepts bearer or `X-Api-Key` auth, enforces concurrency limits,
  applies scoped-key authorization, applies rate and budget decisions, and
  records remote calls.
- `src/deepr/mcp/consult_validation.py` validates consult artifacts for schema,
  trace linkage, capacity posture, forbidden secrets, and no-metered fallback.
- `src/deepr/a2a/consult_tasks.py` requires `allow_metered_api=true` plus a
  positive budget before API-backed A2A consult synthesis.
- `src/deepr/a2a/output_contracts.py` validates published A2A envelope shape
  before host-facing output.

Security invariant:

Host-agent integration must be least privilege by default. Discovery is not
authorization, read access is not write access, and local or plan validation
must not silently fall through to provider APIs.

### Web Dashboard and API Surface

Attacker-controlled inputs:

- API request bodies, query strings, expert names, report IDs, uploaded files,
  provider/model selections, portrait-generation requests, benchmark
  preferences, and confirmation tokens.

Relevant attacker stories:

- A network peer reaches a web API intended for local use and submits paid
  research or deletes demo data.
- A request chooses an unsupported provider/model string to bypass routing or
  cost checks.
- A provider exception leaks internal cost-manager or API error details back to
  a caller.
- A user-triggered portrait request repeatedly calls a paid image API.

Existing controls:

- `src/deepr/web/app.py` uses `DEEPR_API_KEY` bearer or `X-Api-Key` checks for
  API routes when configured and warns that empty auth is for local dev.
- Web provider/model overrides are allowlisted before dispatch.
- `src/deepr/web/portrait_api.py` and related portrait helpers require
  explicit premium image provider intent, acknowledgement of the estimate, and
  create-once behavior unless regeneration is forced.
- `src/deepr/api/middleware/errors.py` returns generic unexpected errors and
  logs sanitized tracebacks.
- `src/deepr/utils/security.py` centralizes path validation, SSRF validation,
  safe path joining, identifier validation, and log redaction.

Security invariant:

Web/API callers must not reach paid calls, destructive demo actions, arbitrary
file paths, or internal exception details without explicit local deployment
intent and the same budget/write gates used by CLI and MCP.

### Provider API, Plan-Quota, and Cost Surface

Attacker-controlled inputs:

- Provider/model selections, user prompts, budgets, batch files, plan backend
  IDs, API-key environment variables, plan CLI output, provider usage payloads,
  and quota probe outputs.

Relevant attacker stories:

- A prompt or compromised host induces repeated premium API calls.
- A plan CLI authenticated by an API key is mistaken for subscription capacity.
- A provider returns missing usage data and Deepr settles a metered call as
  `$0`.
- A cache pre-warm or image-generation path causes silent recurring cost.
- A metered-at-margin CLI is auto-routed as if it were free quota.

Existing controls:

- `src/deepr/core/research.py` validates explicit per-job budgets and reserves
  cost before provider calls, then settles reported usage and refunds failed
  reservations where supported.
- `src/deepr/observability/cost_ledger.py` writes append-only cost events under
  the runtime data root.
- `src/deepr/backends/plan_quota/safety.py` and plan-quota adapters enforce
  auth-mode and no-surprise-bills decisions before explicit plan launches.
- `src/deepr/backends/plan_quota/client.py` records `$0` Deepr cost events and
  quota observations for plan CLI calls and probes.
- Registry pricing and provider-specific usage settlement account for cached
  token buckets and conservative fallback rates where the registry lookup
  cannot safely price a metered path.
- Image generation auto-selects only local `$0` image endpoints by default.
  Premium image APIs require explicit provider choice or the single premium
  auto opt-in.

Security invariant:

Budget is a hard ceiling, not a suggestion. Any path that can spend money or
consume scarce external quota must estimate before dispatch, require explicit
operator intent for premium paths, record usage afterward, and fail closed when
cost cannot be bounded.

### Local Filesystem, Storage, and Artifact Surface

Attacker-controlled inputs:

- Expert names, report IDs, job IDs, filenames, upload names, sandbox IDs,
  source paths, output paths, and generated artifact IDs.

Relevant attacker stories:

- A crafted report ID or filename escapes the configured reports root.
- A document path references files outside an expert's document directory.
- A generated guide or manifest writes bearer tokens into tracked files.
- A local artifact overwrites existing paid output without warning.
- A sandbox ID uses path traversal to read or write outside its workspace.

Existing controls:

- `src/deepr/utils/security.py` provides `validate_path`,
  `safe_path_within`, `validate_path_segment`, file-size limits, file-extension
  checks, URL safety, and log redaction.
- `src/deepr/mcp/state/sandbox.py` validates sandbox paths, file names, token
  limits, and artifact write locations.
- Local storage and report storage validate job IDs and filenames before
  constructing local or blob-backed paths.
- MCP guide and registration-manifest flows redact bearer secrets from
  generated files.
- Portrait writes default to the runtime data root and archive the existing
  portrait before forced replacement.

Security invariant:

Generated or user-supplied identifiers are path data, not filesystem authority.
They must resolve under the intended root, and generated artifacts must never
become a secret-storage mechanism.

### Expert Memory, Graph Commit, and Self-Improvement Surface

Attacker-controlled inputs:

- Source text, extracted claims, verifier outputs, recall candidates,
  consult-quality reviews, monitor proposals, self-model proposals, accepted
  records, graph commit envelopes, and replayed sidecars.

Relevant attacker stories:

- A poisoned source causes a false claim to become a high-confidence durable
  belief.
- A model marks its own output complete and pushes a self-model update that
  grants more authority.
- A lexical or structural signal is treated as proof that a claim is
  hallucinated or true.
- A replayed graph commit writes duplicate state or bypasses idempotency.

Existing controls:

- Graph commit envelopes and apply results are schema-versioned and idempotent.
- Claim verification can carry read-only recall context, but recall remains
  `candidate_only` and cannot itself write graph state.
- Original ideas, hypotheses, concepts, and stance are labeled perspective
  state, not verified external facts.
- Metacognitive monitor proposals preview by default, and accepted self-model
  records require explicit evidence and review before entering learning
  transactions as read-only guidance.
- Consult-quality and hallucination-risk reports are read-only unless a
  separate reviewed promotion command writes an eval or gap artifact.

Security invariant:

Model output may propose knowledge changes, but one explicit, replayable,
auditable write boundary must decide whether state changes. No model should be
able to upgrade its own authority, spend budget, or mark itself trustworthy
without external verification and deterministic gates.

### CI, Dependency, and Developer Workflow Surface

Attacker-controlled inputs:

- Pull requests, dependency updates, fixtures, docs examples, local `.env`
  files, generated logs, release notes, agent scratch files, and CI artifacts.

Relevant attacker stories:

- A fixture contains a key pattern and trains contributors to ignore secret
  scans.
- A test performs a live provider call when no live-test opt-in was intended.
- A doc example encourages a public bind without scoped auth.
- Agent scratch or logs are committed with local state, secrets, or provider
  responses.

Existing controls:

- `.agent/` and `logs/` are ignored. Agent scratch must stay in root `.agent/`.
- Unit tests block outbound network access by default and allow loopback only.
- CI runs ruff, file-size and complexity/security ratchets, strict mypy
  islands, docs consistency checks, Gitleaks history scanning, dependency
  audit, SBOM generation, and GitHub code scanning.
- Integration tests require explicit live-test opt-in.
- Docs require no AI-tool attribution, no emojis, no em dashes, and versioned
  command/schema claims that match CI-derived counts.

Security invariant:

The developer path must be keyless, offline, repeatable, and safe by default.
Anything requiring live provider access or external spend must be explicit and
segregated from the unit gate.

## Severity Calibration

### Critical

A finding is critical when it enables unauthenticated or weakly authenticated
remote access to secrets, durable writes, arbitrary execution, or unbounded
spend.

Examples:

- Public MCP HTTP or web API exposure that lets a reachable peer call mutating
  or paid tools without scoped credentials.
- A budget bypass that allows repeated metered provider or image API calls
  without explicit operator approval and cost-ledger settlement.
- A path traversal that writes executable or configuration content outside the
  configured runtime root.
- A generated MCP registration, guide, log, or release artifact that exposes a
  live bearer token or provider API key.
- A graph-commit or self-model path that lets untrusted model output mutate
  canonical memory or authority without schema and apply gates.

### High

A finding is high when it exposes sensitive expert state, enables a bounded but
material spend path, bypasses host-agent permissions, or lets untrusted content
cross into downstream agent action without contract validation.

Examples:

- A READ_ONLY scoped MCP key can call a sensitive, write, or execute tool.
- A remote A2A consult can select API synthesis without explicit
  `allow_metered_api=true` and a positive budget.
- Provider usage settlement records a real metered call as `$0` because of
  missing registry pricing or missing usage buckets.
- An MCP/A2A output validation gap allows malformed consult artifacts with
  spoofed trace IDs, hidden secrets, or incorrect cost posture.
- An SSRF bypass lets hosted Deepr fetch cloud metadata or internal services
  through a web-search or scrape path.

### Medium

A finding is medium when it weakens auditability, reliability, provenance,
least privilege, or local data isolation, but does not by itself create
unbounded spend, remote code execution, or credential disclosure.

Examples:

- A prompt-injection wrapper is missing around one source-ingestion path, but
  later verifier and write gates still prevent direct memory mutation.
- A cost or quota event is missing for a `$0` plan-quota call, reducing volume
  visibility but not causing dollar spend.
- A generated artifact omits schema version, trace ID, or provenance fields
  required for downstream validation.
- A local-only endpoint gives overbroad data to same-machine callers while
  still requiring local access.
- A denial or exception path logs too much operational context after secret
  redaction but does not expose credentials.

### Low

A finding is low when it affects developer ergonomics, docs safety, local-only
observability, or advisory semantic quality without crossing a security trust
boundary.

Examples:

- A doc example omits a recommended validation command but does not encourage
  unsafe public deployment.
- A local read-only report includes a stale status label while canonical state
  remains intact.
- A hallucination-risk signal is incomplete or noisy but remains advisory,
  read-only, and non-blocking.
- A local test fixture needs clearer fake-key naming but is not a live secret.

### Out Of Scope Or Lower Severity By Design

These are not primary Deepr security findings unless repository code creates a
specific local failure mode:

- Model training data poisoning, model inversion, membership inference, model
  watermarking, confidential GPU serving, and model-weight protection. Deepr
  calls external models; it does not train or host them.
- Generic model hallucination as a standalone security vulnerability. It
  becomes security-relevant only when a Deepr boundary treats model output as
  authority for spend, writes, secrets, permissions, or downstream host action.
- Provider-side outage, billing change, model deprecation, or terms-of-service
  change by itself. Deepr's responsibility is honest detection, explicit
  opt-in, conservative pricing, safe fallback, and clear docs.
- Local operator misuse after explicit warnings, budget confirmations, and
  credentials are intentionally supplied. Deepr should make risky choices
  visible, but it cannot stop an authorized operator from spending their own
  budget.

## Guidance Checked

The following current guidance was checked on 2026-06-30 and used to calibrate
this threat model:

- OWASP Top 10 for LLM Applications 2025:
  <https://genai.owasp.org/llm-top-10/>
- OWASP Agentic AI Threats and Mitigations:
  <https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/>
- MITRE ATLAS:
  <https://atlas.mitre.org/>
- NIST AI 600-1, Artificial Intelligence Risk Management Framework,
  Generative Artificial Intelligence Profile:
  <https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf>
- Model Context Protocol specification 2025-11-25:
  <https://modelcontextprotocol.io/specification/2025-11-25>
- Model Context Protocol security best practices:
  <https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices>
- A2A latest specification:
  <https://a2a-protocol.org/latest/specification/>
