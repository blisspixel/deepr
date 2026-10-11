# First-run configuration, diagnostics, model choice and installation

Issue 204 closes first-run inconsistencies without widening execution or spend
authority. The base is issue 200 commit
`af7369dffef6d0214fd0505db4b918c717d07689` (PR 208), tree
`3743c0cb8d6485c5149d2ba5961df664c5b7100f`, including the research refusal
repairs from PR 207. User-wide configuration remains the default; project
configuration requires the existing explicit selection. Integration uses
issue 203 candidate `3dd102a0f6841537d72df396b14189ab4076f97c`, preserving
its durable checkpoints, refreshed progress and connected-doctor residency
observations alongside these first-run changes.

## Budget and route explanation

Capture requested budget values after configuration/environment/CLI precedence
and before Settings applies its existing fail-closed clamp. Preserve effective
values and report why authority narrowed them. The absolute default ceiling is
$5; init writes conservative requested ceilings of $1/job, $2/day and $5/month;
an unapproved paid policy can make the effective limits $0. Setting numeric
ceilings is not provider authorization. Configuration display must explain
those distinctions rather than recommending budget set as authorization. The
complete human settings formatter is separated from loading/clamping so display
changes do not expand the configuration authority module.

Use the existing research route resolver to display the default research
provider/model. Label compatibility client defaults separately and explain that
route selection does not grant execution: current metered execution is the
explicit attended OpenRouter path after its existing checks. Root and lazy
help must describe that exception consistently. Preserve Click example lines.

## Diagnostics

Summarize required failures separately from advisory, optional and unverified
checks. A skipped local proof is unverified, never ready. Keep provider detail
and deprecated-model warnings limited to configured providers. Reuse the
read-only credential lookup used by keys/research, including stored and
quarantined keys and OpenRouter; never print or log the effective credential.
Doctor adds no inference, release lookup or credential validation operation.

## One selected expert's local model

Local consultation for one explicitly selected profile follows the canonical
local-maintenance resolver: an explicit operation/admitted capacity model,
then a valid local profile model, then DEEPR_LOCAL_MODEL and installed inventory.
This deliberately preserves the existing owner's profile-before-environment
precedence rather than the issue's suggested reversal. Resolve names, aliases
and slugs read-only, without profile migration. Automatic or mixed councils
retain their existing global choice. Selection/discovery stays inside the
consult transaction's deadline, cancellation and proof boundary. An unavailable
pinned model is refused, never silently replaced with a smaller or different
model. Report model-selection provenance where the interface exposes capacity.

## Installation ownership and interpreter

Treat install, repair, update and uninstall guidance as one ownership contract.
Preserve an existing manager; refuse ambiguous ownership rather than creating
duplicate commands. A fresh installation prefers uv and requests managed
CPython 3.13 explicitly. A version request alone does not guarantee management.
Without uv, use an available pipx with an explicitly verified supported stable
interpreter. Do not bootstrap pipx into a venv or externally managed user site.
If neither supported manager is available, provide setup guidance and stop.
Existing release-wheel metadata/download validation remains in place. Repair
and upgrade use the same manager and selected interpreter. No interpreter,
manager or package is installed during this implementation or its tests.

For an existing pipx installation, inspect its reported environment directory
and probe that environment's Python before any package mutation. A supported
stable CPython 3.12-3.14 environment keeps its own base interpreter through
updates and repair. `pipx install --force --python` does not establish a Python
migration. Unsupported or unverifiable environments stop with an explicit
`pipx reinstall deepr-research --python <supported-base-interpreter>` command
and a note to rerun the installer afterward: reinstall restores the recorded
package source, which may be an older release. Uninstall remains available
without this interpreter admission check.
The verified owned interpreter also supplies metadata parsing when PATH has no
supported Python. A fresh pipx installation still requires a supported host;
an unsupported owned environment without one gets a reinstall template and
instructions to supply the newly installed supported interpreter explicitly.

Current primary interfaces:

- [uv Python discovery and managed selection](https://docs.astral.sh/uv/concepts/python-versions/)
- [uv tool environments](https://docs.astral.sh/uv/concepts/tools/)
- [pipx command reference](https://pipx.pypa.io/stable/reference/cli.html)
- [Externally managed Python environments](https://packaging.python.org/en/latest/specifications/externally-managed-environments/)

## Adjacent research boundary failures

Company scrape-only failures must exit nonzero and respect quiet/JSON output
through the existing operation envelope. Exercise the real company orchestrator
with forbidden provider construction and a failing local transport double.
Automatic selection with no usable credentials must return an actionable
failure for single, batch, preview and JSON forms. A valid automatic batch
preview must render every route instead of exiting successfully with no output.
Keep PR 207's configured-admission refusals and all paid/fallback controls.

## Verification and limits

Each increment gets an offline baseline and focused real-boundary regressions.
Installer controls run the real Bash/PowerShell scripts with command/network
shims. Existing affected tests, fast gates and strict islands run before a
frozen patch/hash handoff. The integrated candidate must also pass the full
unit suite with branch coverage and independent coverage enforcement, strict
types, fast checks and hosted platform CI before merge. Tests keep real provider
credentials, paid calls, user installations and daemons outside their boundary.
Local source tracing is the navigation authority; no graph index or live
deployment validation is claimed.
