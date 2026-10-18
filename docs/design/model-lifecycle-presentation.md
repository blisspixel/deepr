# Model lifecycle presentation

Status: implementation, 2026-10-18. Issues #231 and #217.

## Problem and decision

CLI choices advertise shut-down research models. Provider tables conflate
Deepr's retained contracts with current provider recommendations. Gemini 2.5
is restricted to prior users, not shut down. Use the existing registry and
deprecation records to project choices and lifecycle notes. Keep reviewed task
defaults and historical wire identities; candidate metadata does not promote a
model or prove account access.

The CLI choice type advertises only non-shutdown members of its existing
finite model set. Explicit historical members remain accepted with a note on
stderr; unknown names remain invalid. No implicit migration occurs. GPT-5
snapshot notices are informational, with auto-migration disabled. Help derives
retained defaults and preview-only candidates from their owning stores.

Registry access state is independent of provider deprecation. The three stable
Gemini 2.5 contracts become `legacy_access_only`, with a dated source note.
Automatic selection excludes restricted contracts. Explicit identity and
historical pricing remain available, including explicit write-free previews
whose JSON records the access note and unverified account status. Existing dispatch refusal remains until
account eligibility can be proven; it explains access uncertainty instead of
claiming provider shutdown. This correction does not install a Gemini spend or
access verifier. Doctor and provider inventory expose the same note.

Local setup uses the existing VRAM estimator for a documented library model,
showing download size separately from context memory. Unknown or insufficient
capacity yields inspection guidance, not a claim of fit. No download or model
generation is part of setup.

## Alternatives rejected

- Promote the newest provider models: requires the separate adapter and quality
  review gates, and would change execution behavior.
- Remove historical IDs entirely: breaks inspection of retained usage and
  hides the useful provider notice behind a syntax error.
- Treat prior-user access as deprecation or as verified account access: neither
  follows from the provider notice.
- Recommend a large local model on every machine: weight size alone does not
  establish fit at a workload's context length.

## Verification and limits

Offline tests cover advertised choices versus shutdown dates, explicit IDs,
stderr notes, unchanged migration, generated help, selection exclusion,
historical settlement, and dispatch refusal before provider calls. Local setup
tests cover known fit, insufficient VRAM and unknown hardware. Full unit,
coverage, lint, strict types and repository checks precede release. No paid
call or newly eligible production adapter is required or authorized.

Provider sources checked 2026-10-18:

- [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations):
  deep-research shutdown 2026-07-23; original GPT-5 snapshots 2026-12-11.
- [GPT-5](https://developers.openai.com/api/docs/models/gpt-5),
  [Mini](https://developers.openai.com/api/docs/models/gpt-5-mini), and
  [Nano](https://developers.openai.com/api/docs/models/gpt-5-nano): alias snapshots.
- [Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations):
  stable 2.5 prior-user access, no announced shutdown; new-project advice is
  3.5 Flash-Lite or 3.8 Flash.
- [Ollama Qwen3.8](https://ollama.com/library/qwen3.8): 27B tag, 18 GB download.
