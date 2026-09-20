# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.50.18-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.50.18)

**Persistent domain experts built from bounded, auditable research.**

Deepr develops inspectable expert understanding from retained research,
concepts, positions, reasoning, temporal relationships, and experience. It
prefers owned local models, then proven subscription quota, with no automatic
fallback to a paid API.

Deepr is for people and agent teams making recurring decisions in domains that
keep changing. Instead of rebuilding context for every run, they consult the
same inspectable expert state through the CLI or MCP and can see what changed,
what supports a position, and what remains unknown.

Beliefs, sources, graphs, and notes are the expert's cognitive infrastructure,
not the product definition. The product goal is an expert that develops through
study, judgment, prospective predictions, observed outcomes, and review-gated
revision, then performs better on future problems. Deepr now preserves those
inputs as inspectable records; automatic outcome-driven learning and
longitudinal proof of better judgment remain roadmap work.

The next user-facing milestone is **preparation before advice by default**:
check developments relevant to the question and environment, reconsider the
stored perspective, then answer from a dated context. Current consultation
uses stored expert state; explicit fresh-context maintenance is available.
See the [active sequence](ROADMAP.md#active-release-plan) and
[delivery plan](docs/plans/living-expertise.md) for the baseline, preparation,
durable learning, and repeated-use evidence gates.

## Build a durable expert fleet

<p align="center">
  <img src="assets/expert-hub.png" width="100%" alt="Deepr Expert Hub showing a working roster of 49 experts, 25 of them flagship, each card exposing positions, studied findings, retained sources, and recorded stance shifts" />
</p>

The pictured roster is one operator's working set: 49 experts, 25 of them
flagship. Each card exposes positions, studied findings, retained source
counts, and recorded stance shifts from durable state. Flagship membership is
user-curated local state. This is a real local roster, not a clean-install
default and not evidence of improved judgment; grades read thin state honestly,
and `deepr expert health` will say so. See the
[validation record](docs/validation/local-workflows-2026-09-05.md).

## Turn evidence into reusable judgment

<p align="center">
  <img src="assets/expert-profile.png" width="100%" alt="A Deepr Python code quality expert profile showing 6 study sources and 670 findings at $0.00, with each claim carrying its own confidence, source count, and knowledge domain" />
</p>

Expert profiles keep claims, confidence, source lineage, gaps, decisions, and
history inspectable after a research run ends. The structured belief store is
authoritative; reports, digests, and portable exports are regenerable views.

## Keep the spend boundary visible

Local and eligible plan-quota work stay at `$0` marginal API cost. Metered work
never becomes an automatic fallback and cannot turn the local wallet into an
open check.

The aim is bounded *authorized* spend, not zero spend. No surprise bills means
no bill you did not ask for; it does not mean no bills. A cap that can be
exceeded is not a cap, and a cap you cannot raise is not a control, it is a
wall. Deepr prefers local and plan capacity because that is cheapest, not
because paid work is forbidden.

The model is the cloud-platform budget cap: a **total** ceiling, not a blank
cheque and not a recurring allowance. A one-time `$20` cap stops at `$20`
forever; `$20` per month re-arms twelve times a year and is `$240` of annual
exposure, so a non-renewing provider limit is treated as the safer posture
rather than refused for lacking a reset.

| Control | Behaviour |
| --- | --- |
| Default ceiling | `$5.00`, fail-closed |
| Raising it | `DEEPR_MAX_SPEND_CEILING_USD`, set by the operator only |
| Upper bound on a raise | `$100`, so a typo cannot authorize a fortune |
| Lowering it | Honoured, never clamped back up |
| Auditability | The ceiling in force is reported in every contract summary |

Store an OpenRouter key with a hidden prompt, never as a command argument:

```bash
deepr keys set openrouter
deepr keys list
deepr keys check --provider openrouter
deepr budget set 20
deepr budget credits add --amount 20
deepr budget authorize openrouter
```

A stored key is optional paid capacity. `budget set 20` persists the owner
ceiling and the monthly window; it is not spend authority by itself. Wallet
credits are the non-renewing `$20` cap. `budget authorize openrouter` proves
the live key limit is a provider hard stop. MCP, schedules, and automatic
fallback stay blocked. Attended `deepr research --provider openrouter` can
then run one pinned completion under the wallet and ledger.

## Capacity

| Class | Current posture |
| --- | --- |
| Local Ollama | Preferred for expert setup, maintenance, evaluation, and consultation after endpoint ownership is proven. Records $0 and does not consume wallet capacity. |
| Plan quota | Visible/read-only. No production adapter is currently execution-eligible. Claude Code is blocked because managed-policy hooks can survive safe mode; other adapters retain their existing safety blocks. Subscription auth and disabled paid overage alone do not prove process confinement. |
| Metered API | No automatic fallback. Attended `deepr research --provider openrouter` can run one pinned no-tool completion after a stored key, wallet credits, and `budget authorize openrouter`. The attended absorb path still requires verified provider prepaid-no-overage or a hard provider ceiling, plus a cumulative Deepr wallet, a separate finite job ceiling, explicit confirmation, and a durable reservation. Other metered surfaces remain gated. |

A local wallet is cumulative operator authorization, not provider credit. Paid
dispatch also requires authenticated proof of provider-side prepaid capacity or
a hard stop with overage disabled. OpenRouter's current-key limit is that hard
stop for attended one-shot research. Other metered providers stay blocked
until their account-control verifiers land. Funding a wallet, setting a
budget, or approving a prompt cannot enable those other paths.

```bash
deepr capacity
deepr research "A bounded premium question" --provider openai --model o4-mini-deep-research --preview
deepr research "Compare model families" --provider openrouter --model qwen/qwen3.8-flash --preview
deepr research "A bounded premium question" --provider openrouter --model qwen/qwen3.8-flash --limit 0.50
deepr providers openrouter-check
deepr costs doctor
```

OpenRouter catalog slugs can be previewed write-free. Automatic routing, expert
routing, and evaluation stay blocked. Explicit attended research can run one
pinned completion after `deepr budget authorize openrouter`. Omitting `--model`
defaults to `qwen/qwen3.8-flash`. Frontier OpenRouter slugs stay explicit. The public route
check needs no key; the separate current-key check uses a hidden prompt by
default and makes no inference request. An explicit checkout-local `.env`
source is documented for local use. Officially valid nullable limit controls
are reported honestly. A non-renewing total cap is accepted and reconciled
against lifetime usage. A key without a finite BYOK-inclusive limit at or
below the operator ceiling remains ineligible. Key inspection does not itself
fire inference.

See [Capacity and Cost](docs/CAPACITY.md) for the operating and billing
boundary, [Models](docs/MODELS.md#openrouter-preview-catalog) for provider-route
proposals and bounded price classes, and the
[OpenRouter design note](docs/design/openrouter-metered-gateway.md) for the
execution gates that remain.

## Install

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
```

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
```

Installers use the latest verified GitHub Release wheel in an isolated pipx
environment. PyPI publication is not enabled.

## Quick start

```bash
deepr init
deepr doctor --skip-connectivity
deepr capacity
deepr expert make "My Domain Expert" --local -d "The decisions this expert supports"
deepr expert retain "My Domain Expert" ./source.md --title "Trusted starting source"
deepr expert study "My Domain Expert" --local
deepr expert brief "My Domain Expert" --local
deepr expert consult "What should we decide next?" --expert "My Domain Expert" --local
```

Save one UTF-8 source you trust as `source.md` before running the retain step.
Creating a profile is not learning: retain makes the evidence re-readable,
study extracts cited findings, and brief forms the inspectable view that the
consult actually uses. These commands make no paid API call.

Consultation selects bounded literal excerpts around the study's cited source
anchors, including evidence later in a document. Excerpt selection preserves
source references and does not certify that a claim is supported.

See [Quick Start](docs/QUICK_START.md) and [Supported Surface](docs/SUPPORTED_SURFACE.md)
for current workflows. The [MCP Agent Guide](docs/MCP_AGENT_TEST_GUIDE.md)
covers the 36 MCP tools, dual-era `2026-07-28` protocol, and
`deepr mcp conformance`. The [Agent Plugins install guide](docs/INSTALL.md#agent-plugins-hosts)
covers the portable skill and read-only MCP package, host PATH setup, and its
isolated expert workspace. OKF export and the OpenClaw host-profile reference
are documented in [Supported Surface](docs/SUPPORTED_SURFACE.md).

Current compatibility targets are MCP `2026-07-28` with the documented legacy
eras and published Agent Plugins `1.0.0`. See the
[compatibility verification record](docs/validation/research-review-2026-09-13.md)
for tested behavior and the distinction from draft standards and host certification.

## Direction

v2.50.18 adds live OpenRouter key inspection, a binding owner ceiling,
`budget authorize openrouter`, and attended one-shot research under the
wallet and ledger. v2.50.17 added `deepr keys set openrouter`. v2.50.16
added an owner-raisable local spend ceiling and a non-renewing OpenRouter
total cap, plus local Lemonade portraits and the Delve mark. v2.50.15
corrected MCP and Agent Plugins compatibility and blocked Claude plan
execution until managed-policy commands can be confined. It did not enable
skill execution or a claim that expert memory helps.

**Next is v2.51:** one blinded four-arm evaluation of whether a maintained
expert improves repeated decisions versus fresh research, static history, and
compiled state. That measurement comes first because Deepr's product claim is
durable judgment, not a larger agent runtime. Host wiring, expert-authored
skills, and broader paid APIs wait until that evidence exists.

The first rehearsal compares all four arms on the same local model and frozen
sources. It can test the contribution of maintained state under that setup;
it cannot establish superiority over frontier web research. Next, prepare
equal isolated source inventories and bind blinded reviews to exact answers.
The [research assessment](docs/research/deepr-next-evidence-2026-09-13.md)
explains the evidence, remaining gaps, and acceptance criteria.

After that, v2.52 resolves predictions as review-required proposals without
automatic learning. v2.53 finishes the durable parent transaction with
OpenRouter still execution-disabled unless a later explicit rule change and
two-model validation say otherwise. See [what's next and why](ROADMAP.md#active-release-plan).

The [local-first runtime proposal](docs/design/local-first-agent-runtime-options.md)
considers a creator for reusable expert skills and selected OKF knowledge,
plus an optional Cloudflare companion. Local execution and canonical knowledge
remain the default; hosted observation and execution are planned and gated.

## Documentation

- [Approach contract](docs/APPROACH.md) - what the method claims, refuses, and leaves experimental
- [Supported Surface](docs/SUPPORTED_SURFACE.md) - what currently runs
- [Install](docs/INSTALL.md)
- [Quick Start](docs/QUICK_START.md)
- [Capacity and Cost](docs/CAPACITY.md)
- [Experts](docs/EXPERTS.md)
- [MCP Agent Guide](docs/MCP_AGENT_TEST_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Models](docs/MODELS.md)
- [Threat Model](docs/security/THREAT_MODEL.md)
- [Roadmap](ROADMAP.md)
- [Changelog](docs/CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Development

```bash
uv pip install -e ".[dev,full]"
python -m pytest tests/unit/ --ignore=tests/data -q
ruff check src/deepr/
ruff format --check src/deepr/
python scripts/check_file_sizes.py
python scripts/check_ratchets.py
python scripts/check_paid_api_boundaries.py
```

Do not run bare `pytest`: integration tests can contact real providers. The
blocking unit suite requires at least 80 percent branch coverage.

## License

[Apache 2.0](LICENSE)
