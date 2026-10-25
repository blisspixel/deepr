"""Private bounded PyPI acquisition support, with no transaction or command registration.

The 8 KiB header limit is a retained projection limit. Upstream header parsing
uses the pinned transport's existing parser limits, contained by child lifetime.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import struct
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote

from packaging.utils import canonicalize_name
from packaging.version import Version

from deepr.experts.preparation_contracts import PackageCoordinate, PreparationLimits, canonical_bytes, sha256

_FRAME_BYTES = 16384
_HEADER_BYTES = 8192
_READ_BYTES = 4096
_CLEANUP_SECONDS = 5.0
_LATE_REAPERS: set[asyncio.Task[None]] = set()
SourceClass = Literal["pypi_release", "pypi_index"]
_SOURCE_CLASSES: tuple[SourceClass, ...] = ("pypi_release", "pypi_index")


@dataclass(frozen=True)
class RequestIntent:
    sequence: int
    coordinate_id: str
    source_class: SourceClass


@dataclass(frozen=True)
class AcquiredSource:
    intent: RequestIntent
    raw: bytes
    raw_sha256: str
    headers: bytes
    requested_at: str
    observed_at: str
    status_code: int | None
    outcome: str
    parsed_sha256: str | None = None


@dataclass(frozen=True)
class AcquisitionResult:
    sources: tuple[AcquiredSource, ...]
    attempts: int
    decoded_bytes: int
    stop_reason: str
    termination_confirmed: bool
    outstanding_intent: RequestIntent | None
    unreported_read_allowance: int


ReserveIntent = Callable[[RequestIntent], Awaitable[None]]
Launcher = Callable[[], Awaitable[asyncio.subprocess.Process]]


def _endpoint(coordinate: PackageCoordinate, source_class: SourceClass) -> tuple[str, str]:
    if source_class == "pypi_release":
        return (
            f"https://pypi.org/pypi/{quote(coordinate.name, safe='')}/{quote(coordinate.version, safe='')}/json",
            "application/json",
        )
    if source_class == "pypi_index":
        return f"https://pypi.org/simple/{quote(coordinate.name, safe='')}/", "application/vnd.pypi.simple.v1+json"
    raise ValueError("unsupported preparation source class")


def _encoded_frame(message: dict[str, Any]) -> bytes:
    body = canonical_bytes(message)
    if len(body) > _FRAME_BYTES:
        raise ValueError("acquisition IPC frame exceeds bound")
    return struct.pack("!I", len(body)) + body


def _decode_frame(body: bytes) -> dict[str, Any]:
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("acquisition IPC frame must be an object")
    return value


async def _receive(reader: asyncio.StreamReader) -> dict[str, Any]:
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if size > _FRAME_BYTES:
        raise ValueError("acquisition IPC frame exceeds bound")
    return _decode_frame(await reader.readexactly(size))


async def _send(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    writer.write(_encoded_frame(message))
    await writer.drain()


async def _spawn() -> asyncio.subprocess.Process:
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    env.update(
        {
            "PATH": str(Path(sys.executable).parent),
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHON_DOTENV_DISABLED": "1",
        }
    )
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "from deepr.experts.preparation_acquisition import _child_main; _child_main()",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
        creationflags=0x08000000 if os.name == "nt" else 0,
        limit=_FRAME_BYTES + 4,
    )


def _validate_identity(raw: bytes, coordinate: PackageCoordinate, source_class: SourceClass) -> str:
    """Validate form and requested identity, never infer safety or completeness."""
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("source is not an object")
    if source_class == "pypi_release":
        info = parsed.get("info")
        if (
            not isinstance(info, dict)
            or not isinstance(info.get("name"), str)
            or not isinstance(info.get("version"), str)
            or canonicalize_name(info["name"]) != coordinate.name
            or Version(info["version"]) != Version(coordinate.version)
        ):
            raise ValueError("release identity mismatch")
    else:
        meta = parsed.get("meta")
        if (
            not isinstance(meta, dict)
            or not isinstance(meta.get("api-version"), str)
            or re.fullmatch(r"1\.[0-9]+", meta["api-version"]) is None
        ):
            raise ValueError("unsupported index schema")
        if (
            not isinstance(parsed.get("name"), str)
            or canonicalize_name(parsed["name"]) != coordinate.name
            or not isinstance(parsed.get("files"), list)
        ):
            raise ValueError("index project identity mismatch")
    return sha256(canonical_bytes(parsed))


async def _reap_late_process(process: asyncio.subprocess.Process) -> None:
    """Own an eventual launch after admission ended; never send an ACK."""
    _close_and_kill(process)
    try:
        await asyncio.wait_for(process.wait(), timeout=_CLEANUP_SECONDS)
    except (OSError, RuntimeError, TimeoutError):
        # The returned receipt remains unconfirmed; cleanup is not success evidence.
        return


def _own_late_launch(task: asyncio.Task[asyncio.subprocess.Process]) -> None:
    try:
        process = task.result()
    except (asyncio.CancelledError, Exception):
        return
    reaper = asyncio.create_task(_reap_late_process(process))
    _LATE_REAPERS.add(reaper)

    def finished(done: asyncio.Task[None]) -> None:
        _LATE_REAPERS.discard(done)
        if not done.cancelled():
            done.exception()

    reaper.add_done_callback(finished)


@dataclass
class _OperationState:
    """Own cumulative allowances and the single active IPC source transition."""

    coordinates: tuple[PackageCoordinate, ...]
    limits: PreparationLimits
    reserve: ReserveIntent
    sources: list[AcquiredSource]
    attempts: int = 0
    total: int = 0
    current: RequestIntent | None = None
    body: bytes = b""
    headers: bytes = b"{}"
    requested_at: str = ""
    status: int | None = None
    stop: str = "complete"
    read_credit: int = 0
    declared_oversize: bool = False

    @property
    def expected(self) -> list[tuple[PackageCoordinate, SourceClass]]:
        return [(item, kind) for item in self.coordinates for kind in _SOURCE_CLASSES]

    def active(self) -> RequestIntent:
        if self.current is None:
            raise ValueError("acquisition source is not active")
        return self.current

    async def intent(self, message: dict[str, Any], writer: asyncio.StreamWriter) -> None:
        if (
            self.current is not None
            or self.attempts >= min(self.limits.requests, len(self.expected))
            or len(self.sources) >= self.limits.sources
        ):
            raise ValueError("unexpected or exhausted acquisition intent")
        coordinate, source_class = self.expected[self.attempts]
        if message != {"kind": "intent", "coordinate_id": coordinate.coordinate_id, "source_class": source_class}:
            raise ValueError("unadmitted acquisition intent")
        self.current = RequestIntent(self.attempts + 1, coordinate.coordinate_id, source_class)
        self.attempts += 1
        self.body, self.headers = b"", b"{}"
        self.requested_at, self.status = datetime.now(UTC).isoformat(), None
        self.declared_oversize = False
        await self.reserve(self.current)
        await _send(writer, {"ack": True})

    async def header(self, message: dict[str, Any], writer: asyncio.StreamWriter) -> None:
        self.active()
        retained = message.get("headers", {})
        if not isinstance(retained, dict):
            raise ValueError("invalid retained headers")
        self.headers = canonical_bytes(retained)
        if len(self.headers) > _HEADER_BYTES or type(message.get("status")) is not int:
            raise ValueError("invalid retained header projection")
        self.status = cast(int, message["status"])
        length = retained.get("Content-Length")
        if length is not None:
            if not isinstance(length, str) or not length.isascii() or not length.isdigit():
                raise ValueError("invalid declared body length")
            self.declared_oversize = int(length) > min(
                self.limits.per_source_bytes, self.limits.decoded_bytes - self.total
            )

    async def read(self, message: dict[str, Any], writer: asyncio.StreamWriter) -> None:
        self.active()
        if self.read_credit or self.status is None:
            raise ValueError("unexpected read intent")
        self.read_credit = (
            0
            if self.declared_oversize
            else min(_READ_BYTES, self.limits.per_source_bytes - len(self.body), self.limits.decoded_bytes - self.total)
        )
        await _send(writer, {"read_bytes": self.read_credit})

    async def chunk(self, message: dict[str, Any], writer: asyncio.StreamWriter) -> None:
        self.active()
        data = bytes.fromhex(message["hex"])
        if (
            not self.read_credit
            or not data
            or len(data)
            > min(
                self.read_credit, self.limits.per_source_bytes - len(self.body), self.limits.decoded_bytes - self.total
            )
        ):
            raise ValueError("body exceeds acknowledged allowance")
        self.body += data
        self.total += len(data)
        self.read_credit = 0

    def receipt(self, outcome: str, parsed_hash: str | None = None) -> AcquiredSource:
        return AcquiredSource(
            self.active(),
            self.body,
            sha256(self.body),
            self.headers,
            self.requested_at,
            datetime.now(UTC).isoformat(),
            self.status,
            outcome,
            parsed_hash,
        )

    async def done(self, message: dict[str, Any], writer: asyncio.StreamWriter) -> None:
        current = self.active()
        outcome = str(message.get("outcome", "invalid"))
        if outcome != "ok" and self.read_credit:
            # A raw read can consume bytes before raising. Preserve the grant
            # as unknown work and stop before another source can reuse it.
            raise RuntimeError("source failed with unreported body consumption")
        parsed_hash = None
        if outcome == "ok":
            try:
                parsed_hash = _validate_identity(self.body, self.expected[self.attempts - 1][0], current.source_class)
            except (ValueError, TypeError, KeyError):
                outcome = "invalid_metadata"
        self.sources.append(self.receipt(outcome, parsed_hash))
        self.current, self.read_credit = None, 0
        if outcome != "ok":
            self.stop = "partial"

    async def accept(self, message: dict[str, Any], writer: asyncio.StreamWriter) -> bool:
        if message.get("kind") == "finished":
            if self.current is not None or self.attempts != len(self.expected):
                raise ValueError("child omitted planned coordinates")
            return True
        handlers = {
            "intent": self.intent,
            "headers": self.header,
            "read": self.read,
            "body": self.chunk,
            "done": self.done,
        }
        kind = message.get("kind")
        if not isinstance(kind, str) or kind not in handlers:
            raise ValueError("invalid acquisition IPC sequence")
        await handlers[kind](message, writer)
        return False

    def result(self, confirmed: bool) -> AcquisitionResult:
        sources = tuple(self.sources) + ((self.receipt("ambiguous"),) if self.current is not None else ())
        return AcquisitionResult(
            sources,
            self.attempts,
            self.total,
            self.stop,
            confirmed,
            self.current,
            self.read_credit if self.current is not None else 0,
        )


def _close_and_kill(process: asyncio.subprocess.Process) -> bool:
    confirmed = True
    try:
        if process.stdin is not None:
            process.stdin.close()
    except (OSError, RuntimeError):
        confirmed = False
    try:
        if process.returncode is None:
            process.kill()
    except ProcessLookupError:
        pass
    except OSError:
        confirmed = False
    return confirmed


@dataclass
class _ProcessOwner:
    """Own launch cancellation and immediate or eventual child reaping."""

    launcher: Launcher
    process: asyncio.subprocess.Process | None = None
    launch_task: asyncio.Task[asyncio.subprocess.Process] | None = None

    async def start(self) -> asyncio.subprocess.Process:
        async def launch() -> asyncio.subprocess.Process:
            return await self.launcher()

        self.launch_task = asyncio.create_task(launch())
        self.process = await asyncio.shield(self.launch_task)
        return self.process

    async def cleanup(self) -> bool:
        if self.process is None and self.launch_task is not None:
            try:
                self.process = await asyncio.wait_for(asyncio.shield(self.launch_task), timeout=_CLEANUP_SECONDS)
            except (asyncio.CancelledError, Exception):
                self.launch_task.add_done_callback(_own_late_launch)
                return False
        if self.process is None:
            return True
        confirmed = _close_and_kill(self.process)
        try:
            await asyncio.wait_for(asyncio.shield(self.process.wait()), timeout=_CLEANUP_SECONDS)
        except (TimeoutError, asyncio.CancelledError, OSError, RuntimeError):
            return False
        return confirmed


async def _run_protocol(state: _OperationState, owner: _ProcessOwner) -> None:
    process = await owner.start()
    if process.stdin is None or process.stdout is None:
        raise ValueError("acquisition child requires pipes")
    await _send(process.stdin, {"coordinates": [item.model_dump() for item in state.coordinates]})
    while not await state.accept(await _receive(process.stdout), process.stdin):
        pass


async def acquire_pypi(
    coordinates: tuple[PackageCoordinate, ...],
    *,
    limits: PreparationLimits,
    reserve_intent: ReserveIntent,
    launcher: Launcher = _spawn,
) -> AcquisitionResult:
    """One operation allowance; durable reservation finishes before any ACK.

    This helper is neither caller authentication nor live admission. Cleanup
    may take an additional bounded wait, reported separately by confirmation.
    """
    if not 1 <= len(coordinates) <= 3 or len({item.name for item in coordinates}) != len(coordinates):
        raise ValueError("one to three distinct admitted projects required")
    coordinates = tuple(PackageCoordinate.model_validate_json(canonical_bytes(item)) for item in coordinates)
    limits = PreparationLimits.model_validate_json(canonical_bytes(limits))
    state = _OperationState(coordinates, limits, reserve_intent, [])
    owner = _ProcessOwner(launcher)
    cancelled = False
    try:
        await asyncio.wait_for(_run_protocol(state, owner), timeout=limits.acquisition_seconds)
    except asyncio.CancelledError:
        state.stop, cancelled = "cancelled", True
    except TimeoutError:
        state.stop = "deadline"
    except Exception:
        state.stop = "failed"
    finally:
        confirmed = await owner.cleanup()
    result = state.result(confirmed)
    if cancelled:
        raise AcquisitionCancelled(result)
    return result


class AcquisitionCancelled(asyncio.CancelledError):
    def __init__(self, result: AcquisitionResult) -> None:
        super().__init__("preparation acquisition cancelled")
        self.result = result


def _sync_receive() -> dict[str, Any]:
    def exact(size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            part = sys.stdin.buffer.read(size - len(data))
            if not part:
                raise EOFError("acquisition parent closed")
            data.extend(part)
        return bytes(data)

    size = struct.unpack("!I", exact(4))[0]
    if size > _FRAME_BYTES:
        raise ValueError("oversized parent frame")
    return _decode_frame(exact(size))


def _sync_send(message: dict[str, Any]) -> None:
    sys.stdout.buffer.write(_encoded_frame(message))
    sys.stdout.buffer.flush()


def _stream_response(response: Any) -> str:
    while True:
        _sync_send({"kind": "read"})
        count = _sync_receive().get("read_bytes")
        if type(count) is not int or not 0 <= count <= _READ_BYTES:
            raise ValueError("invalid body allowance")
        if count == 0:
            return "byte_limit"
        data = response.raw.read(count, decode_content=False)
        if not data:
            return "ok"
        _sync_send({"kind": "body", "hex": data.hex()})


def _response_admission(response: Any, media: str) -> str | None:
    encoding = str(response.headers.get("Content-Encoding", "identity")).strip().lower()
    content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
    if response.status_code != 200:
        return "http_refused"
    if encoding not in ("identity", ""):
        return "encoding_refused"
    return None if content_type == media else "media_refused"


def _fetch_source(coordinate: PackageCoordinate, source_class: SourceClass) -> str:
    """One pinned request and undecoded body stream, after parent admission."""
    from deepr.utils.pinned_http import close_pinned_response, pinned_get

    response = None
    try:
        url, media = _endpoint(coordinate, source_class)
        response = pinned_get(
            url,
            stream=True,
            allow_redirects=False,
            address_failover=False,
            redact_request_target=True,
            timeout=(5, 5),
            headers={"Accept": media, "Accept-Encoding": "identity"},
        )
        retained = {
            key: str(response.headers[key])
            for key in ("Date", "Last-Modified", "ETag", "Content-Type", "Content-Encoding", "Content-Length")
            if key in response.headers
        }
        if len(canonical_bytes(retained)) > _HEADER_BYTES:
            raise ValueError("retained header projection exceeds bound")
        _sync_send({"kind": "headers", "headers": retained, "status": response.status_code})
        return _response_admission(response, media) or _stream_response(response)
    except Exception:
        return "failed"
    finally:
        if response is not None:
            close_pinned_response(response)


def _child_main() -> None:
    """Fixed trusted downloader. No model, tool, descendants or private inputs."""
    spec = _sync_receive()
    if (
        set(spec) != {"coordinates"}
        or not isinstance(spec["coordinates"], list)
        or not 1 <= len(spec["coordinates"]) <= 3
    ):
        raise ValueError("invalid acquisition child specification")
    coordinates = [PackageCoordinate.model_validate(item) for item in spec["coordinates"]]
    for coordinate in coordinates:
        for source_class in _SOURCE_CLASSES:
            _sync_send({"kind": "intent", "coordinate_id": coordinate.coordinate_id, "source_class": source_class})
            if _sync_receive() != {"ack": True}:
                return
            _sync_send({"kind": "done", "outcome": _fetch_source(coordinate, source_class)})
    _sync_send({"kind": "finished"})
