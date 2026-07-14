"""Durable admission helpers for metered expert-chat provider calls.

When live metered chat is enabled, every provider completion must reserve a
ceiling, mark dispatch before the network call, and settle or conservatively
consume the hold afterward. Owned-capacity backends never enter this module.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, TypeVar

from deepr.services.metered_call import execute_reserved_async_call, execute_reserved_async_stream

T = TypeVar("T")

_ACCOUNTING_EXTRA_KEYS = frozenset({"max_cost_per_job"})
_DEFAULT_OUTPUT_TOKEN_CAP = 4096
_DEFAULT_OUTPUT_PRICE_PER_1M = 10.0


def split_accounting_extra(extra: Mapping[str, Any]) -> tuple[dict[str, Any], float | None]:
    """Remove accounting-only fields so provider params stay pure."""
    cleaned = {key: value for key, value in extra.items() if key not in _ACCOUNTING_EXTRA_KEYS}
    raw_ceiling = extra.get("max_cost_per_job")
    if raw_ceiling is None:
        return cleaned, None
    if isinstance(raw_ceiling, bool) or not isinstance(raw_ceiling, (int, float)):
        raise ValueError("max_cost_per_job must be a positive finite number")
    ceiling = float(raw_ceiling)
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise ValueError("max_cost_per_job must be a positive finite number")
    return cleaned, ceiling


def apply_output_token_ceiling(
    provider_extra: dict[str, Any],
    *,
    model: str,
    max_cost_per_job: float | None,
    default_cap: int = _DEFAULT_OUTPUT_TOKEN_CAP,
) -> dict[str, Any]:
    """Bound max_tokens from the dollar ceiling when the caller did not set one.

    Uses half the call ceiling for output so input tokens keep headroom. Caps at
    ``default_cap``. Existing explicit max_tokens / max_completion_tokens win.
    """
    if max_cost_per_job is None:
        return provider_extra
    if "max_tokens" in provider_extra or "max_completion_tokens" in provider_extra:
        return provider_extra
    try:
        from deepr.providers.registry import get_token_pricing

        output_price = float(get_token_pricing(model).get("output", _DEFAULT_OUTPUT_PRICE_PER_1M))
    except Exception:
        output_price = _DEFAULT_OUTPUT_PRICE_PER_1M
    if not math.isfinite(output_price) or output_price <= 0:
        output_price = _DEFAULT_OUTPUT_PRICE_PER_1M
    spendable = max_cost_per_job * 0.5
    tokens = int((spendable / output_price) * 1_000_000)
    bounded = max(1, min(int(default_cap), tokens))
    return {**provider_extra, "max_tokens": bounded}


async def execute_metered_chat_provider_call(
    *,
    provider: str,
    model: str,
    source: str,
    max_cost_per_job: float | None,
    call: Callable[[], Awaitable[T]],
) -> T:
    """Run one metered expert-chat provider call under durable admission."""
    return await execute_reserved_async_call(
        operation_prefix="expert-chat",
        provider=provider,
        model=model,
        source=source,
        call=call,
        max_cost_per_job=max_cost_per_job,
    )


def execute_metered_chat_provider_stream(
    *,
    provider: str,
    model: str,
    source: str,
    max_cost_per_job: float | None,
    events: Callable[[], AsyncIterator[tuple[T, object | None]]],
) -> AsyncIterator[T]:
    """Stream one metered expert-chat provider call under durable admission."""
    return execute_reserved_async_stream(
        operation_prefix="expert-chat",
        provider=provider,
        model=model,
        source=source,
        events=events,
        max_cost_per_job=max_cost_per_job,
    )


__all__ = [
    "apply_output_token_ceiling",
    "execute_metered_chat_provider_call",
    "execute_metered_chat_provider_stream",
    "split_accounting_extra",
]
