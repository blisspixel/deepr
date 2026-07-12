from __future__ import annotations

import subprocess

import pytest

from deepr.backends.local_capacity import (
    LocalCapacityState,
    probe_local_gpu_occupancy,
)


def _completed(stdout: str, *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["nvidia-smi"], returncode, stdout=stdout, stderr=stderr)


def test_nvidia_probe_reports_free_below_threshold():
    captured = {}

    def run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _completed("0, 4\n1, 22\n")

    observation = probe_local_gpu_occupancy(which=lambda _: "C:/NVIDIA/nvidia-smi.exe", run=run)

    assert observation.state == LocalCapacityState.FREE
    assert observation.gpu_utilization_percent == (4.0, 22.0)
    assert captured["argv"] == [
        "C:/NVIDIA/nvidia-smi.exe",
        "--query-gpu=index,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    assert captured["kwargs"]["timeout"] == 2.0


def test_nvidia_probe_reports_meaningful_contention_as_busy():
    observation = probe_local_gpu_occupancy(
        which=lambda _: "/usr/bin/nvidia-smi",
        run=lambda *args, **kwargs: _completed("0, 35\n"),
    )

    assert observation.state == LocalCapacityState.BUSY
    assert "peak utilization 35%" in observation.detail


@pytest.mark.parametrize(
    ("which", "runner", "detail"),
    [
        (lambda _: None, None, "not available"),
        (
            lambda _: "nvidia-smi",
            lambda *args, **kwargs: _completed("", returncode=1, stderr="driver unavailable"),
            "exited 1",
        ),
        (lambda _: "nvidia-smi", lambda *args, **kwargs: _completed("not,csv,enough\n"), "malformed"),
    ],
)
def test_nvidia_probe_degrades_honestly_to_unknown(which, runner, detail):
    kwargs = {"which": which}
    if runner is not None:
        kwargs["run"] = runner

    observation = probe_local_gpu_occupancy(**kwargs)

    assert observation.state == LocalCapacityState.UNKNOWN
    assert detail in observation.detail


def test_nvidia_probe_timeout_is_unknown_not_failure():
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("nvidia-smi", timeout=2.0)

    observation = probe_local_gpu_occupancy(which=lambda _: "nvidia-smi", run=timeout)

    assert observation.state == LocalCapacityState.UNKNOWN
    assert "failed" in observation.detail


def test_probe_never_queries_resident_vram():
    captured = {}

    def run(argv, **kwargs):
        captured["argv"] = argv
        return _completed("0, 0\n")

    observation = probe_local_gpu_occupancy(which=lambda _: "nvidia-smi", run=run)

    assert observation.state == LocalCapacityState.FREE
    assert all("memory" not in argument for argument in captured["argv"])


def test_probe_validates_bounds_before_invocation():
    with pytest.raises(ValueError, match="busy_threshold_percent"):
        probe_local_gpu_occupancy(busy_threshold_percent=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        probe_local_gpu_occupancy(timeout_seconds=0)
