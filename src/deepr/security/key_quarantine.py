"""Drop metered API keys out of Deepr's own process at startup.

Deepr already strips these keys from every plan-quota child process, by name,
before launching it. That protects the subprocess. It does not protect the
parent: an API key set in the *operating system* environment is visible to
Deepr itself for the whole run, and any code path that constructs a metered
client can read it.

The gap is easy to miss because removing a key from `.env` looks like removing
it. Measured on this machine: after renaming every key in `.env`, three were
still live in the process - `OPENAI_API_KEY`, `XAI_API_KEY` and
`ANTHROPIC_API_KEY` - because they are set at the Windows user level and `.env`
was never their only source. Anyone auditing their own setup by editing
`.env` would conclude they had disarmed something they had not.

So this quarantines them at the process boundary instead. Called once at CLI
startup, before any command runs: every known metered key name is moved out of
``os.environ`` and preserved under a ``DEEPR_QUARANTINED_`` prefix, so nothing
is destroyed and an operator who genuinely wants to spend can still recover it
deliberately.

**Why moving beats trusting the guards.** The existing protections - the $0
ceiling, the child-env stripping, the auth-mode detection - are all checks that
have to be *reached*. This removes the material instead. A check can be
bypassed by a new code path that nobody remembered to route through it; an
environment variable that is not set cannot be read by any code path at all.
That is the difference between a policy and a property.

It is deliberately reversible and deliberately loud. ``DEEPR_ALLOW_METERED_KEYS``
opts out for anyone whose workflow genuinely needs a metered client in-process,
because a safety measure with no escape hatch gets disabled wholesale rather
than adjusted.
"""

from __future__ import annotations

import os

QUARANTINE_PREFIX = "DEEPR_QUARANTINED_"

OPT_OUT_VAR = "DEEPR_ALLOW_METERED_KEYS"
"""Set truthy to leave metered keys in place for this process."""

METERED_KEY_NAMES: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_FOUNDRY_API_KEY",
    "AZURE_API_KEY",
    "ANTIGRAVITY_API_KEY",
    "CODEX_API_KEY",
    "KIRO_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "PERPLEXITY_API_KEY",
    "TOGETHER_API_KEY",
    "OPENROUTER_API_KEY",
)
"""Every variable a provider SDK reads to bill someone.

Wider than the set the plan-quota adapters strip, because those only need to
cover the providers behind the plan CLIs. This runs in Deepr's own process,
where any client library that happens to be importable could pick one up.
"""

_TRUTHY = {"1", "true", "yes", "on"}


def _opted_out(env: dict[str, str]) -> bool:
    return str(env.get(OPT_OUT_VAR, "")).strip().lower() in _TRUTHY


def quarantine_metered_keys(env: dict[str, str] | None = None) -> list[str]:
    """Move metered keys out of the environment. Returns the names moved.

    Mutates ``os.environ`` by default, which is the point: it must affect the
    running process, not a copy of its environment.

    Preserved rather than deleted. An operator who has approved a spend should
    be able to recover the value they set, and silently destroying a
    credential someone put there on purpose would be its own kind of surprise.
    """
    target = os.environ if env is None else env
    if _opted_out(target):
        return []

    moved: list[str] = []
    for name in METERED_KEY_NAMES:
        value = target.get(name)
        if not value or not value.strip():
            continue
        target[QUARANTINE_PREFIX + name] = value
        del target[name]
        moved.append(name)
    return moved


def quarantined_names(env: dict[str, str] | None = None) -> list[str]:
    """Which keys this process moved aside, for reporting."""
    target = os.environ if env is None else env
    return sorted(
        name.removeprefix(QUARANTINE_PREFIX) for name in target if name.startswith(QUARANTINE_PREFIX)
    )


def live_metered_names(env: dict[str, str] | None = None) -> list[str]:
    """Metered keys still readable in this process.

    Should be empty after startup. Anything here is a key a provider SDK could
    pick up, and the honest answer to "can this bill me" is no only when this
    list is empty or the operator opted out on purpose.
    """
    target = os.environ if env is None else env
    return sorted(name for name in METERED_KEY_NAMES if str(target.get(name, "")).strip())
