"""Safety primitives for destructive and subprocess-backed web actions."""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, TypeVar, cast

from flask import jsonify

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEMO_ACTION_LOCK = Lock()
BENCHMARK_COST_VALIDATION_ERROR = "Approved benchmark cost must be a non-negative number"
_Handler = TypeVar("_Handler", bound=Callable[..., Any])


def benchmark_command(*arguments: str) -> list[str]:
    """Build a CWD-independent command for the trusted benchmark script."""
    return [sys.executable, str(_PROJECT_ROOT / "scripts" / "benchmark_models.py"), *arguments]


def benchmark_project_root() -> str:
    """Return the repository root expected by benchmark runtime paths."""
    return str(_PROJECT_ROOT)


def approved_benchmark_cost(value: object) -> float:
    """Validate the user-approved maximum benchmark cost in dollars."""
    if isinstance(value, bool):
        raise ValueError(BENCHMARK_COST_VALIDATION_ERROR)
    if not isinstance(value, (int, float, str)):
        raise ValueError(BENCHMARK_COST_VALIDATION_ERROR)
    try:
        cost = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(BENCHMARK_COST_VALIDATION_ERROR) from exc
    if not math.isfinite(cost) or cost < 0:
        raise ValueError(BENCHMARK_COST_VALIDATION_ERROR)
    return cost


def approved_benchmark_command(tier: str, value: object) -> list[str]:
    """Build a benchmark command with matching preflight and runtime caps."""
    cost = str(approved_benchmark_cost(value))
    return benchmark_command(
        "--tier", tier, "--save", "--emit-routing-config", "--budget", cost, "--max-estimated-cost", cost
    )


def parse_benchmark_estimate(output: str) -> tuple[float, int, int]:
    """Parse the exact benchmark JSON dry-run contract or fail closed."""
    try:
        contract = next(
            line.removeprefix("DEEPR_BENCHMARK_ESTIMATE_JSON=")
            for line in reversed(output.splitlines())
            if line.startswith("DEEPR_BENCHMARK_ESTIMATE_JSON=")
        )
        payload = json.loads(contract)
        estimated_cost = approved_benchmark_cost(payload["estimated_cost"])
        model_count = int(payload["model_count"])
        provider_count = int(payload["provider_count"])
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid benchmark estimate output") from exc
    if model_count < 0 or provider_count < 0:
        raise ValueError("Invalid benchmark estimate output")
    return estimated_cost, model_count, provider_count


def serialize_demo_action(handler: _Handler) -> _Handler:
    """Reject overlapping destructive demo mutations with HTTP 409."""

    @wraps(handler)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if not _DEMO_ACTION_LOCK.acquire(blocking=False):
            return jsonify({"error": "Another demo data operation is already running."}), 409
        try:
            return handler(*args, **kwargs)
        finally:
            _DEMO_ACTION_LOCK.release()

    return cast(_Handler, guarded)
