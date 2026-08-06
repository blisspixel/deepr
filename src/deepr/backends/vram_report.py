"""Report what is actually using VRAM, and what that costs in model choice.

A study pass that quietly picks a weaker model because 8 GB of a 24 GB card is
held by a browser and a screen recorder is making a decision the operator would
almost certainly overrule if they could see it. "Free VRAM is 16 GB" is not
actionable; "these processes hold 8 GB, and closing them admits a 24B model" is.

Windows note: under WDDM, nvidia-smi cannot attribute VRAM per process and
reports N/A for each. The process list and the total are still reliable, so this
reports which applications are attached to the GPU and the aggregate they hold,
without inventing per-process numbers it cannot measure.

Pure reporting. No model call, no network, no mutation.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

# Applications that commonly hold hundreds of MB and that an operator can close
# without losing work in progress. Used only to order suggestions; anything not
# listed is still reported, just not singled out.
_COMMONLY_RECLAIMABLE = (
    "obs64",
    "chrome",
    "msedge",
    "firefox",
    "discord",
    "slack",
    "teams",
    "powerpnt",
    "excel",
    "winword",
    "nvidia overlay",
    "githubdesktop",
    "docker desktop",
    "chatgpt",
    "spotify",
    "steam",
)


@dataclass
class VramReport:
    """GPU memory totals plus the processes attached to the device."""

    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    gpu_name: str = ""
    processes: list[str] = field(default_factory=list)
    per_process_available: bool = False
    detail: str = ""

    @property
    def reclaimable_candidates(self) -> list[str]:
        """Attached processes an operator could plausibly close."""
        seen: set[str] = set()
        out: list[str] = []
        for name in self.processes:
            lowered = name.lower()
            for token in _COMMONLY_RECLAIMABLE:
                if token in lowered and token not in seen:
                    seen.add(token)
                    out.append(name)
                    break
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu": self.gpu_name,
            "total_bytes": self.total_bytes,
            "used_bytes": self.used_bytes,
            "free_bytes": self.free_bytes,
            "process_count": len(self.processes),
            "per_process_available": self.per_process_available,
            "reclaimable_candidates": self.reclaimable_candidates,
            "detail": self.detail,
        }


def _run_nvidia_smi(args: list[str]) -> str:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return ""
    try:
        result = subprocess.run(  # noqa: S603 - resolved absolute path, fixed argv
            [binary, *args], capture_output=True, text=True, timeout=15
        )
    except Exception:
        return ""
    return result.stdout if result.returncode == 0 else ""


def collect_vram_report() -> VramReport:
    """Read GPU totals and attached processes. Never raises."""
    totals = _run_nvidia_smi(["--query-gpu=name,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"])
    if not totals.strip():
        return VramReport(detail="nvidia-smi unavailable; VRAM could not be measured")

    first = totals.strip().splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < 4:
        return VramReport(detail="unexpected nvidia-smi output")
    try:
        report = VramReport(
            gpu_name=parts[0],
            total_bytes=int(float(parts[1]) * 1024 * 1024),
            used_bytes=int(float(parts[2]) * 1024 * 1024),
            free_bytes=int(float(parts[3]) * 1024 * 1024),
        )
    except ValueError:
        return VramReport(detail="could not parse nvidia-smi memory values")

    apps = _run_nvidia_smi(["--query-compute-apps=pid,used_memory,name", "--format=csv,noheader"])
    names: list[str] = []
    per_process = False
    for line in apps.strip().splitlines():
        fields = [f.strip() for f in line.split(",", 2)]
        if len(fields) < 3:
            continue
        if fields[1] and fields[1] not in {"[N/A]", "N/A"}:
            per_process = True
        raw = fields[2]
        if raw.startswith("[") or not raw:
            continue
        names.append(raw.rsplit("\\", 1)[-1].rsplit("/", 1)[-1])
    report.processes = names
    report.per_process_available = per_process
    if names and not per_process:
        report.detail = (
            "Per-process VRAM is unavailable on this platform (WDDM), so only the "
            "aggregate and the attached process list are reported."
        )
    return report


def describe_headroom(report: VramReport, *, needed_bytes: int) -> list[str]:
    """Explain, in operator terms, what the current VRAM state costs.

    Returns lines to print. Empty when there is nothing worth saying.
    """
    if report.total_bytes <= 0:
        return [report.detail] if report.detail else []

    lines = [
        f"GPU: {report.gpu_name} - {report.total_bytes / 1e9:.1f} GB total, "
        f"{report.free_bytes / 1e9:.1f} GB free ({report.used_bytes / 1e9:.1f} GB in use)."
    ]
    if report.used_bytes > 2_000_000_000 and report.processes:
        lines.append(
            f"{len(report.processes)} process(es) are attached to the GPU, holding "
            f"{report.used_bytes / 1e9:.1f} GB between them."
        )
        candidates = report.reclaimable_candidates
        if candidates:
            lines.append("Closing these would return VRAM: " + ", ".join(candidates[:8]))
    if needed_bytes > report.free_bytes and needed_bytes <= report.total_bytes:
        shortfall = needed_bytes - report.free_bytes
        lines.append(
            f"A better model needs about {needed_bytes / 1e9:.1f} GB; that is "
            f"{shortfall / 1e9:.1f} GB more than is free, but it would fit on an idle card."
        )
    if report.detail:
        lines.append(report.detail)
    return lines
