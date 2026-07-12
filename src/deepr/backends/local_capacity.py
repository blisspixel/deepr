"""Read-only local accelerator occupancy for scheduled maintenance.

The probe is deliberately best-effort. A confirmed busy observation can defer
scheduled local work, while missing platform support remains visible as
``unknown`` and never disables local execution.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

LOCAL_CAPACITY_OBSERVATION_SCHEMA_VERSION = "deepr-local-capacity-observation-v1"
DEFAULT_LOCAL_GPU_BUSY_THRESHOLD_PERCENT = 35.0
DEFAULT_LOCAL_GPU_PROBE_TIMEOUT_SECONDS = 2.0


class LocalCapacityState(str, Enum):
    FREE = "free"
    BUSY = "busy"
    UNKNOWN = "unknown"


class LocalCapacityUnavailableReason(str, Enum):
    GPU_BUSY = "local_gpu_busy"


@dataclass(frozen=True)
class LocalCapacityObservation:
    """One point-in-time read-only occupancy observation."""

    state: LocalCapacityState
    source: str
    detail: str
    gpu_utilization_percent: tuple[float, ...] = ()
    busy_threshold_percent: float = DEFAULT_LOCAL_GPU_BUSY_THRESHOLD_PERCENT
    schema_version: str = LOCAL_CAPACITY_OBSERVATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "source": self.source,
            "detail": self.detail,
            "gpu_utilization_percent": list(self.gpu_utilization_percent),
            "busy_threshold_percent": self.busy_threshold_percent,
            "read_only": True,
            "cost_usd": 0.0,
        }


RunProbe = Callable[..., subprocess.CompletedProcess[str]]
WhichProbe = Callable[[str], str | None]


def _unknown(detail: str, *, threshold: float) -> LocalCapacityObservation:
    return LocalCapacityObservation(
        state=LocalCapacityState.UNKNOWN,
        source="nvidia-smi",
        detail=detail,
        busy_threshold_percent=threshold,
    )


def _parse_nvidia_utilization(output: str) -> tuple[float, ...] | None:
    samples: list[float] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2:
            return None
        try:
            int(fields[0])
            utilization = float(fields[1])
        except ValueError:
            return None
        if not 0.0 <= utilization <= 100.0:
            return None
        samples.append(utilization)
    return tuple(samples) if samples else None


def probe_local_gpu_occupancy(
    *,
    which: WhichProbe = shutil.which,
    run: RunProbe = subprocess.run,
    timeout_seconds: float = DEFAULT_LOCAL_GPU_PROBE_TIMEOUT_SECONDS,
    busy_threshold_percent: float = DEFAULT_LOCAL_GPU_BUSY_THRESHOLD_PERCENT,
) -> LocalCapacityObservation:
    """Return a read-only best-effort local GPU occupancy observation.

    NVIDIA utilization is the first supported signal. Resident VRAM is not
    queried or used because an idle Ollama model commonly remains loaded.
    Missing or malformed platform support is reported honestly as ``unknown``.
    """
    if not 0.0 < busy_threshold_percent <= 100.0:
        raise ValueError("busy_threshold_percent must be greater than 0 and at most 100")
    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")

    executable = which("nvidia-smi")
    if executable is None:
        return _unknown("nvidia-smi is not available; local GPU occupancy is unknown", threshold=busy_threshold_percent)

    argv = [
        executable,
        "--query-gpu=index,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = run(
            argv,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _unknown(f"nvidia-smi occupancy probe failed: {exc}", threshold=busy_threshold_percent)

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()
        suffix = f": {detail}" if detail else ""
        return _unknown(
            f"nvidia-smi occupancy probe exited {completed.returncode}{suffix}",
            threshold=busy_threshold_percent,
        )

    samples = _parse_nvidia_utilization(completed.stdout or "")
    if samples is None:
        return _unknown("nvidia-smi returned malformed utilization output", threshold=busy_threshold_percent)

    peak = max(samples)
    state = LocalCapacityState.BUSY if peak >= busy_threshold_percent else LocalCapacityState.FREE
    verdict = "busy" if state == LocalCapacityState.BUSY else "free"
    return LocalCapacityObservation(
        state=state,
        source="nvidia-smi",
        detail=(
            f"local GPU capacity is {verdict}: peak utilization {peak:g}% "
            f"across {len(samples)} GPU(s), busy threshold {busy_threshold_percent:g}%"
        ),
        gpu_utilization_percent=samples,
        busy_threshold_percent=busy_threshold_percent,
    )


__all__ = [
    "DEFAULT_LOCAL_GPU_BUSY_THRESHOLD_PERCENT",
    "LOCAL_CAPACITY_OBSERVATION_SCHEMA_VERSION",
    "LocalCapacityObservation",
    "LocalCapacityState",
    "LocalCapacityUnavailableReason",
    "probe_local_gpu_occupancy",
]
