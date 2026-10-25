"""Synthetic acquisition fixtures; no public source is contacted."""

import asyncio
import json
import struct
import sys
from types import SimpleNamespace

import pytest

from deepr.experts import preparation_acquisition as acquisition
from deepr.experts.preparation_contracts import PackageCoordinate, PreparationLimits, sha256

COORDINATE = PackageCoordinate(name="fixture-project", version="1.0")


class Writer:
    def __init__(self):
        self.messages = []
        self.closed = False

    def write(self, data):
        self.messages.append(acquisition._decode_frame(data[4:]))

    async def drain(self):
        pass

    def close(self):
        self.closed = True


class Child:
    def __init__(self, messages):
        self.stdin = Writer()
        self.stdout = asyncio.StreamReader()
        for message in messages:
            self.stdout.feed_data(acquisition._encoded_frame(message))
        self.stdout.feed_eof()
        self.returncode = None
        self.killed = False

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


def response_messages(source_class, raw):
    return [
        {"kind": "intent", "coordinate_id": COORDINATE.coordinate_id, "source_class": source_class},
        {"kind": "headers", "headers": {"Content-Type": "application/json"}, "status": 200},
        {"kind": "read"},
        {"kind": "body", "hex": raw.hex()},
        {"kind": "done", "outcome": "ok"},
    ]


def payloads():
    return (
        b'{ "info": {"name":"fixture-project","version":"1.0"}, "urls": [] }',
        b'{"name":"fixture-project","meta":{"api-version":"1.1"},"files":[]}',
    )


@pytest.mark.asyncio
async def test_cumulative_receipts_bind_raw_and_separate_parsed_identities():
    release, index = payloads()
    child = Child(
        response_messages("pypi_release", release) + response_messages("pypi_index", index) + [{"kind": "finished"}]
    )
    reservations = []

    async def reserve(intent):
        assert not any(message.get("ack") for message in child.stdin.messages[1:]) if not reservations else True
        reservations.append(intent)

    async def launch():
        return child

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "complete"
    assert result.attempts == len(reservations) == 2
    assert result.decoded_bytes == len(release) + len(index)
    assert result.sources[0].raw == release
    assert result.sources[0].raw_sha256 == sha256(release)
    assert result.sources[0].parsed_sha256 != result.sources[0].raw_sha256
    assert result.termination_confirmed and child.killed
    spec = child.stdin.messages[0]
    assert set(spec) == {"coordinates"}
    assert "question" not in json.dumps(spec)


@pytest.mark.asyncio
async def test_failed_durable_reservation_never_acknowledges_dispatch():
    child = Child(response_messages("pypi_release", payloads()[0]))

    async def reserve(intent):
        raise OSError("synthetic durable storage failure")

    async def launch():
        return child

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "failed"
    assert result.attempts == 1 and result.outstanding_intent is not None
    assert not any(message.get("ack") for message in child.stdin.messages)
    assert result.decoded_bytes == 0 and child.killed


@pytest.mark.asyncio
async def test_byte_allowance_rejects_over_credit_without_retaining_excess():
    raw = payloads()[0]
    child = Child(response_messages("pypi_release", raw))

    async def reserve(intent):
        pass

    async def launch():
        return child

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(per_source_bytes=5), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "failed"
    assert result.decoded_bytes == 0
    assert {"read_bytes": 5} in child.stdin.messages
    assert result.sources[0].outcome == "ambiguous"


@pytest.mark.asyncio
async def test_oversized_ipc_prefix_refuses_before_body_allocation():
    child = Child([])
    child.stdout = asyncio.StreamReader()
    child.stdout.feed_data(struct.pack("!I", acquisition._FRAME_BYTES + 1))

    async def reserve(intent):
        raise AssertionError("no request admitted")

    async def launch():
        return child

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "failed" and result.attempts == 0 and child.killed


@pytest.mark.asyncio
async def test_real_blocked_child_is_killed_and_awaited_at_total_deadline():
    children = []

    async def launch():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        children.append(process)
        return process

    async def reserve(intent):
        pass

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(acquisition_seconds=1), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "deadline" and result.termination_confirmed
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_cancellation_preserves_result_and_awaits_child():
    child = Child([])
    child.stdout = asyncio.StreamReader()

    async def reserve(intent):
        pass

    async def launch():
        return child

    task = asyncio.create_task(
        acquisition.acquire_pypi((COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(acquisition.AcquisitionCancelled) as caught:
        await task
    assert caught.value.result.termination_confirmed
    assert child.killed


@pytest.mark.parametrize(
    "kind,raw",
    [
        ("pypi_release", b'{"info":{"name":"other","version":"1.0"}}'),
        ("pypi_index", b'{"name":"fixture-project","meta":{"api-version":"2.0"},"files":[]}'),
        ("pypi_index", b'{"name":"other","meta":{"api-version":"1.0"},"files":[]}'),
    ],
)
def test_metadata_identity_does_not_turn_malformed_source_into_success(kind, raw):
    with pytest.raises(ValueError):
        acquisition._validate_identity(raw, COORDINATE, kind)


def test_endpoints_only_use_admitted_coordinates():
    assert acquisition._endpoint(COORDINATE, "pypi_release") == (
        "https://pypi.org/pypi/fixture-project/1.0/json",
        "application/json",
    )
    with pytest.raises(ValueError):
        acquisition._endpoint(COORDINATE, "arbitrary_url")


@pytest.mark.parametrize(
    "headers,status,expected",
    [
        ({"Content-Type": "application/json", "Content-Encoding": "gzip"}, 200, "encoding_refused"),
        ({"Content-Type": "text/html"}, 200, "media_refused"),
        ({"Content-Type": "application/json", "Location": "https://private.invalid"}, 302, "http_refused"),
    ],
)
def test_child_pinned_transport_refuses_encoding_media_redirect_without_read(monkeypatch, headers, status, expected):
    from deepr.utils import pinned_http

    messages = []
    inputs = iter([{"coordinates": [COORDINATE.model_dump()]}, {"ack": True}, {"ack": True}])
    calls = []

    class Raw:
        def read(self, *args, **kwargs):
            raise AssertionError("refused body must not be read")

    response = SimpleNamespace(headers=headers, status_code=status, raw=Raw())

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr(acquisition, "_sync_receive", lambda: next(inputs))
    monkeypatch.setattr(acquisition, "_sync_send", messages.append)
    monkeypatch.setattr(pinned_http, "pinned_get", get)
    monkeypatch.setattr(pinned_http, "close_pinned_response", lambda value: None)
    acquisition._child_main()
    assert next(item["outcome"] for item in messages if item["kind"] == "done") == expected
    assert all(call[1]["address_failover"] is False and call[1]["allow_redirects"] is False for call in calls)
    assert all(call[1]["headers"]["Accept-Encoding"] == "identity" for call in calls)
    assert all(call[1]["redact_request_target"] is True for call in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_stage", ["dns", "stream"])
async def test_real_fixed_worker_boundary_contains_blocked_transport_and_slow_stream(blocked_stage):
    children = []
    code = """
import time
from types import SimpleNamespace
from deepr.utils import pinned_http
from deepr.experts.preparation_acquisition import _child_main
class Raw:
    def read(self, count, decode_content=False):
        time.sleep(0.02)
        return b"x"
def get(*args, **kwargs):
    if BLOCKED_STAGE == "dns":
        time.sleep(60)
    return SimpleNamespace(status_code=200, headers={"Content-Type":"application/json"}, raw=Raw())
pinned_http.pinned_get = get
pinned_http.close_pinned_response = lambda response: None
_child_main()
""".replace("BLOCKED_STAGE", repr(blocked_stage))

    async def launch():
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        children.append(child)
        return child

    reserved = []

    async def reserve(intent):
        reserved.append(intent)

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(acquisition_seconds=2), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "deadline"
    assert result.termination_confirmed and children[0].returncode is not None
    assert len(reserved) == result.attempts == 1
    assert result.outstanding_intent == reserved[0]
    assert result.sources[0].outcome == "ambiguous"
    if blocked_stage == "dns":
        assert result.decoded_bytes == result.unreported_read_allowance == 0
    else:
        assert result.decoded_bytes > 0
        assert result.unreported_read_allowance == acquisition._READ_BYTES


@pytest.mark.asyncio
async def test_declared_oversize_body_is_refused_before_first_read_credit():
    messages = response_messages("pypi_release", b"not used")
    messages[1]["headers"]["Content-Length"] = "9999999"
    child = Child(messages)

    async def reserve(intent):
        pass

    async def launch():
        return child

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "failed"
    assert {"read_bytes": 0} in child.stdin.messages
    assert result.decoded_bytes == 0


@pytest.mark.asyncio
async def test_default_child_launch_environment_excludes_credentials_and_private_inputs(monkeypatch):
    observed = {}

    async def create(*args, **kwargs):
        observed.update(kwargs)
        return Child([])

    monkeypatch.setenv("OPENAI_API_KEY", "private-synthetic")
    monkeypatch.setenv("HTTPS_PROXY", "private-synthetic")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    await acquisition._spawn()
    assert "OPENAI_API_KEY" not in observed["env"]
    assert "HTTPS_PROXY" not in observed["env"]
    assert observed["env"]["PYTHON_DOTENV_DISABLED"] == "1"
    assert observed["stderr"] == asyncio.subprocess.DEVNULL


@pytest.mark.asyncio
async def test_cleanup_failure_retains_receipt_and_refuses_termination_claim():
    class UnconfirmedChild(Child):
        def kill(self):
            raise OSError("synthetic termination failure")

        async def wait(self):
            raise OSError("synthetic wait failure")

    child = UnconfirmedChild([])

    async def reserve(intent):
        pass

    async def launch():
        return child

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "failed"
    assert result.termination_confirmed is False


@pytest.mark.asyncio
async def test_late_launch_retains_cleanup_owner_after_uncertain_return(monkeypatch):
    monkeypatch.setattr(acquisition, "_CLEANUP_SECONDS", 0.01)
    release_launch = asyncio.Event()
    entered_launch = asyncio.Event()
    child = Child([])

    async def launch():
        entered_launch.set()
        await release_launch.wait()
        return child

    async def reserve(intent):
        raise AssertionError("late process must not dispatch")

    task = asyncio.create_task(
        acquisition.acquire_pypi((COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch)
    )
    await entered_launch.wait()
    task.cancel()
    with pytest.raises(acquisition.AcquisitionCancelled) as caught:
        await task
    assert caught.value.result.termination_confirmed is False
    assert caught.value.result.attempts == 0
    assert not child.killed
    release_launch.set()
    for _ in range(20):
        await asyncio.sleep(0.01)
        if child.killed and not acquisition._LATE_REAPERS:
            break
    assert child.killed and child.stdin.closed
    assert child.stdin.messages == []
    assert not acquisition._LATE_REAPERS
    assert caught.value.result.termination_confirmed is False


@pytest.mark.asyncio
async def test_raw_read_failure_preserves_consumed_grant_and_blocks_next_source():
    children = []
    code = """
from types import SimpleNamespace
from deepr.utils import pinned_http
from deepr.experts.preparation_acquisition import _child_main
class Raw:
    def __init__(self):
        self.calls = 0
    def read(self, count, decode_content=False):
        self.calls += 1
        if self.calls == 1:
            return b"known"
        consumed_before_error = b"unreported partial bytes"
        raise OSError("synthetic read failed after partial consumption")
pinned_http.pinned_get = lambda *args, **kwargs: SimpleNamespace(status_code=200, headers={"Content-Type":"application/json"}, raw=Raw())
pinned_http.close_pinned_response = lambda response: None
_child_main()
"""

    async def launch():
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        children.append(child)
        return child

    reserved = []

    async def reserve(intent):
        reserved.append(intent)

    result = await acquisition.acquire_pypi(
        (COORDINATE,), limits=PreparationLimits(), reserve_intent=reserve, launcher=launch
    )
    assert result.stop_reason == "failed"
    assert result.attempts == len(reserved) == 1
    assert len(result.sources) == 1
    assert result.sources[0].outcome == "ambiguous"
    assert result.sources[0].raw == b"known"
    assert result.decoded_bytes == 5
    assert result.unreported_read_allowance == acquisition._READ_BYTES
    assert result.outstanding_intent == reserved[0]
    assert result.termination_confirmed and children[0].returncode is not None


@pytest.mark.parametrize(
    "source_class,payload",
    [
        ("pypi_release", {"info": {"name": 123, "version": "1"}}),
        ("pypi_release", {"info": {"name": "123", "version": 1}}),
        ("pypi_release", {"info": {"name": ["123"], "version": "1"}}),
        ("pypi_index", {"name": 123, "meta": {"api-version": "1.4"}, "files": []}),
        ("pypi_index", {"name": "123", "meta": {"api-version": 1}, "files": []}),
        ("pypi_index", {"name": "123", "meta": {"api-version": "1.garbage"}, "files": []}),
        ("pypi_index", {"name": "123", "meta": {"api-version": "1"}, "files": []}),
    ],
)
def test_identity_requires_actual_string_fields_and_numeric_index_version(source_class, payload):
    coordinate = PackageCoordinate(name="123", version="1")
    with pytest.raises(ValueError):
        acquisition._validate_identity(json.dumps(payload).encode(), coordinate, source_class)


@pytest.mark.parametrize("api_version", ["1.0", "1.4", "1.999"])
def test_numeric_index_minor_is_retained_without_rejecting_new_minor(api_version):
    payload = {"name": COORDINATE.name, "meta": {"api-version": api_version}, "files": []}
    raw = json.dumps(payload).encode()
    assert acquisition._validate_identity(raw, COORDINATE, "pypi_index")
    assert json.loads(raw)["meta"]["api-version"] == api_version
