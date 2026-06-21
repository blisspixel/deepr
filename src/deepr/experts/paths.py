"""Canonical on-disk location for an expert's data.

All of an expert's state - profile, beliefs, loop runs, subscriptions,
conversations, documents - must live under ONE directory so the expert is a
single coherent unit on disk. That directory is the sanitized, lowercased
("slug") form of the expert name: filesystem-safe and case-stable across
Windows/macOS, while the human-readable name is carried inside ``profile.json``.

Every store resolves through here so they can never disagree. The bug this fixes:
``ExpertStore`` slugified the directory (``sanitize_name(name).lower()``) while
``BeliefStore``/loop-runs used the raw display name, so one expert was split
across two directories (profile in ``ai_expert/``, beliefs in ``AI Expert/``).
"""

from __future__ import annotations

from pathlib import Path

from deepr.utils.security import sanitize_name, validate_path


def expert_slug(name: str) -> str:
    """The filesystem-safe, case-stable directory name for an expert."""
    return sanitize_name(name).lower()


def canonical_expert_dir(name: str, base_path: Path | None = None) -> Path:
    """Resolve an expert's canonical data directory (containment-checked).

    ``base_path`` defaults to the configured experts root. The name is sanitized
    and lowercased; ``validate_path`` guarantees the result stays inside the root
    (so untrusted names like ``../other`` cannot escape).
    """
    if base_path is None:
        from deepr.config import experts_root

        base_path = experts_root()
    return validate_path(expert_slug(name), base_dir=base_path, must_exist=False, allow_create=True)
