"""Bounded, read-only Linux DRM device observations, with honest unknowns.

AMD's documented occupancy and dedicated VRAM counters are not a measurement
of shared system-memory capacity. Intel detection does not imply perf access.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DrmDevice:
    card: str
    driver: str
    vendor: str
    device: str
    utilization_percent: float | None = None
    vram_total_bytes: int | None = None
    vram_used_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "source": "linux-drm-sysfs", "read_only": True}


def _text(path: Path) -> str:
    try:
        with path.open(encoding="ascii") as stream:
            return stream.read(128).strip()
    except (OSError, UnicodeError):
        return ""


def _counter(path: Path) -> int | None:
    text = _text(path)
    return int(text) if re.fullmatch(r"[0-9]{1,20}", text) else None


def read_drm_devices(root: Path = Path("/sys/class/drm")) -> tuple[DrmDevice, ...]:
    try:
        cards = sorted(path for path in root.iterdir() if re.fullmatch(r"card[0-9]+", path.name))[:16]
    except OSError:
        return ()
    devices: list[DrmDevice] = []
    for card in cards:
        directory = card / "device"
        if not directory.exists():
            continue
        try:
            driver = (directory / "driver").resolve(strict=True).name
        except OSError:
            driver = "unknown"
        busy = _counter(directory / "gpu_busy_percent") if driver == "amdgpu" else None
        total = _counter(directory / "mem_info_vram_total") if driver == "amdgpu" else None
        used = _counter(directory / "mem_info_vram_used") if driver == "amdgpu" else None
        if total is None or total <= 0 or used is None or used > total:
            total, used = None, None
        devices.append(
            DrmDevice(
                card.name,
                driver,
                _text(directory / "vendor"),
                _text(directory / "device"),
                float(busy) if busy is not None and busy <= 100 else None,
                total,
                used,
            )
        )
    return tuple(devices)


def observe_ollama_residency(base_url: str | None = None) -> list[dict[str, Any]]:
    """GET running-model placement only, through the owned-local trust boundary."""
    import os

    import httpx

    from deepr.backends.capacity import _OLLAMA_DEFAULT_URL, validate_owned_local_ollama_url

    try:
        endpoint = validate_owned_local_ollama_url(base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL)
        with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
            response = client.get(f"{endpoint}/api/ps")
            response.raise_for_status()
            payload = response.json()
        entries = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []
        result: list[dict[str, Any]] = []
        for entry in entries[:32]:
            if not isinstance(entry, dict):
                continue
            name, size, vram = entry.get("name"), entry.get("size"), entry.get("size_vram")
            if not isinstance(name, str) or not 0 < len(name) <= 256:
                continue
            if type(size) is not int or size <= 0 or type(vram) is not int or not 0 <= vram <= size:
                continue
            digest = entry.get("digest")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                continue
            result.append(
                {
                    "model": name,
                    "digest": digest,
                    "size_bytes": size,
                    "gpu_bytes": vram,
                    "gpu_residency_percent": round(vram / size * 100, 1),
                    "source": "ollama:/api/ps",
                }
            )
        return result
    except (OSError, ValueError, httpx.HTTPError):
        return []
