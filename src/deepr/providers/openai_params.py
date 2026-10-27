"""OpenAI chat parameter compatibility for the GPT-5 family.

GPT-5 family models accept only the default sampling temperature and take
``max_completion_tokens`` instead of the legacy ``max_tokens``.
"""

from collections.abc import Mapping
from typing import Any


def accepts_sampling_params(model: str) -> bool:
    """Whether ``model`` accepts non-default temperature/top_p."""
    return not model.startswith("gpt-5")


def compatible_chat_kwargs(model: str, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Return chat kwargs with unsupported GPT-5 parameters removed or renamed."""
    params = dict(kwargs)
    if accepts_sampling_params(model):
        return params
    params.pop("temperature", None)
    params.pop("top_p", None)
    if "max_tokens" in params:
        legacy = params.pop("max_tokens")
        params.setdefault("max_completion_tokens", legacy)
    return params
