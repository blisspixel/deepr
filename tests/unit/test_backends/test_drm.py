"""AMD counters, Intel unknowns and owned-local resident-model reporting."""

import httpx
import pytest

from deepr.backends import drm, local_capacity, vram_report
from deepr.backends.local_capacity import LocalCapacityState


def device(root, *, card="card1", driver="amdgpu", busy="97", total="2147483648", used="1217351680"):
    target = root / "drivers" / driver
    target.mkdir(parents=True, exist_ok=True)
    directory = root / card / "device"
    directory.mkdir(parents=True)
    (directory / "driver").symlink_to(target, target_is_directory=True)
    for key, value in {
        "vendor": "0x1002",
        "device": "0x15bf",
        "gpu_busy_percent": busy,
        "mem_info_vram_total": total,
        "mem_info_vram_used": used,
    }.items():
        (directory / key).write_text(value)
    return directory


def test_amd_numeric_occupancy_and_vram_are_read_without_mutation(tmp_path, monkeypatch):
    directory = device(tmp_path)
    before = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    devices = drm.read_drm_devices(tmp_path)
    monkeypatch.setattr(local_capacity, "read_drm_devices", lambda: devices)
    observation = local_capacity.probe_local_gpu_occupancy(which=lambda _: None)
    assert observation.state == LocalCapacityState.BUSY
    assert observation.gpu_utilization_percent == (97.0,)
    assert observation.to_dict()["devices"][0]["vram_total_bytes"] == 2147483648
    assert before == {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    monkeypatch.setattr(vram_report, "read_drm_devices", lambda: devices)
    monkeypatch.setattr(vram_report, "_run_nvidia_smi", lambda _: "")
    report = vram_report.collect_vram_report()
    assert report.total_bytes == 2147483648
    assert report.used_bytes == 1217351680
    assert report.shared_memory
    assert report.processes == []
    assert "shared" in report.detail


@pytest.mark.parametrize("busy", ["-1", "101", "NaN", "", "0.5", "999999999999999999999999"])
def test_invalid_amd_counter_remains_unknown(tmp_path, busy):
    device(tmp_path, busy=busy)
    assert drm.read_drm_devices(tmp_path)[0].utilization_percent is None


@pytest.mark.parametrize("driver", ["i915", "xe"])
def test_intel_is_visible_without_fabricating_numeric_occupancy(tmp_path, monkeypatch, driver):
    device(tmp_path, driver=driver)
    devices = drm.read_drm_devices(tmp_path)
    assert devices[0].driver == driver
    assert devices[0].utilization_percent is None
    assert devices[0].vram_total_bytes is None
    monkeypatch.setattr(local_capacity, "read_drm_devices", lambda: devices)
    observation = local_capacity.probe_local_gpu_occupancy(which=lambda _: None)
    assert observation.state == LocalCapacityState.UNKNOWN
    assert driver in observation.detail


def test_idle_resident_amd_memory_does_not_mean_busy_and_unknown_device_prevents_all_free(tmp_path, monkeypatch):
    device(tmp_path, busy="0")
    monkeypatch.setattr(local_capacity, "read_drm_devices", lambda: drm.read_drm_devices(tmp_path))
    assert local_capacity.probe_local_gpu_occupancy(which=lambda _: None).state == LocalCapacityState.FREE
    device(tmp_path, card="card2", driver="i915")
    assert local_capacity.probe_local_gpu_occupancy(which=lambda _: None).state == LocalCapacityState.UNKNOWN


def test_unsupported_platform_is_empty(tmp_path):
    assert drm.read_drm_devices(tmp_path / "missing") == ()


def test_ollama_residency_is_get_only_and_uses_owned_local_transport(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, json={"models": [{"name": "fixture", "digest": "a" * 64, "size": 1000, "size_vram": 750}]}
        )

    real_client = httpx.Client
    options = []

    def client(**kwargs):
        options.append(kwargs)
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    observed = drm.observe_ollama_residency("http://127.0.0.1:11434")
    assert observed[0]["gpu_residency_percent"] == 75
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/ps"
    assert "authorization" not in requests[0].headers
    assert options == [{"timeout": 2.0, "trust_env": False, "follow_redirects": False}]


@pytest.mark.parametrize(
    "endpoint", ["https://example.com", "http://192.168.1.2:11434", "http://user:secret@localhost:11434"]
)
def test_residency_rejects_unowned_endpoints_before_transport(monkeypatch, endpoint):
    monkeypatch.setattr(httpx, "Client", lambda **_: pytest.fail("Unowned endpoint reached transport"))
    assert drm.observe_ollama_residency(endpoint) == []


def test_doctor_amd_headroom_does_not_claim_cpu_execution(tmp_path, monkeypatch):
    from deepr.cli.commands.doctor import _check_local_gpu_headroom

    device(tmp_path)
    devices = drm.read_drm_devices(tmp_path)
    monkeypatch.setattr(vram_report, "read_drm_devices", lambda: devices)
    monkeypatch.setattr(vram_report, "_run_nvidia_smi", lambda _: "")
    monkeypatch.setattr(local_capacity, "read_drm_devices", lambda: devices)
    check = _check_local_gpu_headroom()
    assert check.passed
    assert "97% busy" in " ".join(check.details)
    assert "still run on CPU" not in " ".join(check.details)
