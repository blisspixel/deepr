"""Plan-quota CLI adapter registry (ROADMAP Phase 6).

Each entry describes one vendor coding/agent CLI that Deepr can drive as a
subprocess to run quality-tolerant expert maintenance on capacity the operator
already pays for, instead of a metered API call. The shared machinery
(``cli_runner``, ``safety``, ``client``) is backend-agnostic; everything
vendor-specific lives here as data plus a small ``argv`` builder per CLI:

- the headless invocation (verified against each vendor's June 2026 docs);
- which env vars mean "a metered API key is set" (the auth-mode guard);
- the exhaustion signature (so a depleted plan reschedules instead of failing);
- the cost/window model and one quota unit name;
- whether Deepr may *auto-route* to it (``enabled_by_default``) or it is
  explicit-only behind a printed ToS/billing note.

Honesty rules baked in (AGENTIC_BALANCE.md, the ROADMAP STOP banner):
``enabled_by_default`` is False for any CLI that is metered per use (Copilot),
ToS gray-zone for headless/subscription use (Antigravity, Grok subscription), or
whose vendor prohibits third-party-harness use (Kiro). Those still run via an
explicit ``--plan <id>`` behind the safety gate and a printed note, but Deepr
never auto-routes to them or counts them as free capacity. Uncertain June-2026
surfaces (Antigravity's non-TTY stdout drop, Grok's undocumented exhaustion
string) are flagged ``experimental`` and should be re-verified on the target
machine - vendor CLIs churn quarterly.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import QuotaWindowKind

# Strip ANSI escape sequences some TUIs leak into captured stdout.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# A fenced ```...``` block the model wrapped its answer/JSON in.
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\n(.*)\n```$", re.DOTALL)


@dataclass(frozen=True)
class PlanQuotaAdapter:
    """A declarative spec for driving one vendor CLI as a research backend."""

    backend_id: str
    display_name: str
    exe: str
    cost_model: CostModel
    window_kind: QuotaWindowKind
    unit_name: str
    argv_builder: Callable[[str, str | None], list[str]]
    metered_env_vars: tuple[str, ...] = ()
    exhaustion_signals: tuple[str, ...] = ()
    enabled_by_default: bool = False
    metered_at_margin: bool = False
    experimental: bool = False
    needs_pty: bool = False
    tos_note: str = ""
    value_note: str = ""

    def build_argv(self, prompt: str, model: str | None = None) -> list[str]:
        return self.argv_builder(prompt, model)

    def looks_exhausted(self, text: str) -> bool:
        low = text.lower()
        return any(sig in low for sig in self.exhaustion_signals)

    def parse_answer(self, stdout: str) -> str:
        """Extract a clean text answer from captured stdout.

        All supported CLIs print the final answer to stdout as text (codex and
        claude stream progress to stderr; the others run non-TUI in headless
        mode). We strip ANSI noise and a wrapping code fence, then trim.
        """
        text = _ANSI_RE.sub("", stdout).strip()
        fenced = _FENCE_RE.match(text)
        if fenced:
            text = fenced.group(1).strip()
        return text


def _append_model(args: list[str], model_flag: str | None, model: str | None) -> list[str]:
    if model_flag and model:
        return [*args, model_flag, model]
    return args


# --- per-CLI argv builders (prompt + optional model -> argv) ----------------
# Verified against June 2026 vendor docs (see the research notes in the PR).


def _codex_argv(prompt: str, model: str | None) -> list[str]:
    # `codex exec` is the non-interactive subcommand; stdout = final message,
    # stderr = progress. read-only sandbox + never-approve = a safe text answer.
    args = [
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "--skip-git-repo-check",
    ]
    return [*_append_model(args, "--model", model), prompt]


def _claude_argv(prompt: str, model: str | None) -> list[str]:
    # `claude -p` is print/non-interactive. No tools are granted, so it answers
    # as text. Plan window again post the 2026-06-15 reversal.
    args = _append_model(["claude"], "--model", model)
    return [*args, "-p", prompt]


def _opencode_argv(prompt: str, model: str | None) -> list[str]:
    # `opencode run` is the sanctioned non-interactive entry. BYO-provider:
    # always pass an explicit provider/model so the run is deterministic.
    args = _append_model(["opencode", "run"], "-m", model)
    return [*args, prompt]


def _kiro_argv(prompt: str, model: str | None) -> list[str]:
    # `kiro-cli chat --no-interactive` prints to stdout and exits. read,grep
    # tools only - a research answer must not write or run shell.
    args = ["kiro-cli", "chat", "--no-interactive", "--trust-tools=read,grep"]
    return [*_append_model(args, "--model", model), prompt]


def _grok_argv(prompt: str, model: str | None) -> list[str]:
    # Grok Build. --no-auto-update/--no-alt-screen for scripts; --always-approve
    # so a headless run never hangs on a tool-approval prompt.
    args = ["grok", "--no-auto-update", "--no-alt-screen", "--always-approve"]
    args = _append_model(args, "--model", model)
    return [*args, "-p", prompt]


def _antigravity_argv(prompt: str, model: str | None) -> list[str]:
    # `agy -p`. Known non-TTY stdout-drop bug (June 2026): captured stdout may
    # be empty even on exit 0 - the client treats empty output as an error.
    args = _append_model(["agy"], "--model", model)
    return [*args, "-p", prompt]


def _copilot_argv(prompt: str, model: str | None) -> list[str]:
    # `copilot -p ... -s` = response-only. deny shell+write: a research answer,
    # never a code action. Metered since 2026-06-01, so off by default.
    args = ["copilot", "-p", prompt, "-s", "--no-ask-user", "--deny-tool", "shell,write"]
    if model:
        args += ["--model", model]
    return args


# --- the registry -----------------------------------------------------------

_ADAPTERS: tuple[PlanQuotaAdapter, ...] = (
    PlanQuotaAdapter(
        backend_id="codex",
        display_name="Codex CLI (ChatGPT plan)",
        exe="codex",
        cost_model=CostModel.ROLLING_WINDOW,
        window_kind=QuotaWindowKind.ROLLING_5H,
        unit_name="plan_request",
        argv_builder=_codex_argv,
        metered_env_vars=("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"),
        exhaustion_signals=("usage_limit_reached", "5-hour message limit", "weekly limit", "429"),
        enabled_by_default=True,
        value_note="flat ChatGPT plan, 5h rolling windows: $0 at the margin for batched research",
    ),
    PlanQuotaAdapter(
        backend_id="claude",
        display_name="Claude Code (Pro/Max plan)",
        exe="claude",
        cost_model=CostModel.ROLLING_WINDOW,
        window_kind=QuotaWindowKind.ROLLING_5H,
        unit_name="plan_request",
        argv_builder=_claude_argv,
        metered_env_vars=("ANTHROPIC_API_KEY",),
        exhaustion_signals=("usage limit", "rate limit", "plan limit", "429"),
        enabled_by_default=True,
        value_note="Pro/Max plan window (headless billing reverted 2026-06-15): $0 at the margin",
    ),
    PlanQuotaAdapter(
        backend_id="opencode",
        display_name="OpenCode CLI (BYO provider)",
        exe="opencode",
        cost_model=CostModel.CREDIT_POOL,
        window_kind=QuotaWindowKind.MONTHLY_CREDIT_POOL,
        unit_name="provider_call",
        argv_builder=_opencode_argv,
        # BYO-provider: pass -m and route to an oauth/subscription or local
        # model. A bare API key for the chosen provider is the metered path.
        metered_env_vars=(),
        exhaustion_signals=("rate limit", "quota", "insufficient credit", "429"),
        enabled_by_default=True,
        value_note="routes to an OAuth/subscription provider or a local model for $0/prepaid runs",
        tos_note="cost depends on the routed provider; pass -m and prefer an OAuth or local model",
    ),
    PlanQuotaAdapter(
        backend_id="kiro",
        display_name="Kiro CLI",
        exe="kiro-cli",
        cost_model=CostModel.CALENDAR_WINDOW,
        window_kind=QuotaWindowKind.MONTHLY_CREDIT_POOL,
        unit_name="credit",
        argv_builder=_kiro_argv,
        metered_env_vars=(),
        exhaustion_signals=("credits_exhausted", "429"),
        enabled_by_default=False,
        tos_note=(
            "Kiro's terms permit CI/CD automation but PROHIBIT third-party-harness use; "
            "review the AUP before driving it from Deepr. Overage is off by default."
        ),
        value_note="monthly credits, overage off by default (hard cap)",
    ),
    PlanQuotaAdapter(
        backend_id="grok",
        display_name="Grok Build (xAI)",
        exe="grok",
        cost_model=CostModel.CREDIT_POOL,
        window_kind=QuotaWindowKind.MONTHLY_CREDIT_POOL,
        unit_name="plan_request",
        argv_builder=_grok_argv,
        # XAI_API_KEY selects the metered xAI API path; subscription auth lives
        # in ~/.grok/auth.json. Block when the key is set.
        metered_env_vars=("XAI_API_KEY",),
        exhaustion_signals=("rate limit", "quota", "credits", "429"),
        enabled_by_default=False,
        experimental=True,
        tos_note=(
            "subscription (SuperGrok/X Premium+) headless use is ToS gray-zone; xAI steers "
            "automation to the metered API key. Verify the exhaustion signature on your build."
        ),
        value_note="SuperGrok/X Premium+ subscription quota (gray-zone for headless use)",
    ),
    PlanQuotaAdapter(
        backend_id="antigravity",
        display_name="Antigravity CLI (Google plan)",
        exe="agy",
        cost_model=CostModel.CALENDAR_WINDOW,
        window_kind=QuotaWindowKind.WEEKLY,
        unit_name="compute_unit",
        argv_builder=_antigravity_argv,
        metered_env_vars=("GEMINI_API_KEY", "ANTIGRAVITY_API_KEY"),
        exhaustion_signals=("quota reached", "resets in", "429"),
        enabled_by_default=False,
        experimental=True,
        needs_pty=True,
        tos_note=(
            "automated/headless use is ToS gray-zone amid an active account-ban wave; "
            "the CLI also drops stdout under a non-TTY pipe (June 2026). Use at your own risk."
        ),
        value_note="Google AI plan weekly compute cap, hard-stop (no overage)",
    ),
    PlanQuotaAdapter(
        backend_id="copilot",
        display_name="GitHub Copilot CLI",
        exe="copilot",
        cost_model=CostModel.CREDIT_POOL,
        window_kind=QuotaWindowKind.MONTHLY_CREDIT_POOL,
        unit_name="ai_credit",
        argv_builder=_copilot_argv,
        metered_env_vars=(),
        exhaustion_signals=("rate limit", "quota", "insufficient", "402", "429"),
        enabled_by_default=False,
        metered_at_margin=True,
        tos_note=(
            "usage-based billing since 2026-06-01 (per-token AI credits): NOT free at the margin. "
            "Disable/cap org overage to avoid surprise spend."
        ),
        value_note="metered per token (no plan advantage over the API)",
    ),
)

REGISTRY: dict[str, PlanQuotaAdapter] = {a.backend_id: a for a in _ADAPTERS}


def get_adapter(backend_id: str) -> PlanQuotaAdapter | None:
    return REGISTRY.get(backend_id)


def all_adapters() -> tuple[PlanQuotaAdapter, ...]:
    return _ADAPTERS


def auto_routable_adapters() -> tuple[PlanQuotaAdapter, ...]:
    """Adapters Deepr may auto-route to (genuinely $0-at-margin, ToS-clean)."""
    return tuple(a for a in _ADAPTERS if a.enabled_by_default)
