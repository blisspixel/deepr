"""Tests for deepr.backends.plan_quota.cli_runner.

Uses real hermetic subprocesses via ``sys.executable`` (cross-platform, fast, no
vendor CLI needed) so the runner's launch/timeout/exit-code handling is exercised
for real rather than mocked.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

import pytest

from deepr.backends.plan_quota import cli_runner as plan_quota_cli_runner
from deepr.backends.plan_quota.cli_runner import _clean_argv, _kill_process_tree, run_cli


def _process_exists(pid: int) -> bool:
    if os.name == "nt":
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return f'"{pid}"' in listing.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_test_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


class TestRunCli:
    async def test_captures_stdout(self):
        result = await run_cli([sys.executable, "-c", "import sys; sys.stdout.write('hello')"])
        assert result.ok
        assert result.stdout == "hello"
        assert result.returncode == 0
        assert result.duration_ms >= 0

    async def test_feeds_stdin(self):
        result = await run_cli(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
            stdin="piped-prompt",
        )
        assert result.ok
        assert result.stdout == "piped-prompt"

    async def test_separates_stderr(self):
        result = await run_cli(
            [sys.executable, "-c", "import sys; sys.stderr.write('progress'); sys.stdout.write('answer')"]
        )
        assert result.stdout == "answer"
        assert "progress" in result.stderr

    async def test_accepts_exact_raw_byte_limit_without_truncating_multibyte_text(self, monkeypatch):
        monkeypatch.setattr(plan_quota_cli_runner, "MAX_CAPTURE_BYTES", 8)

        result = await run_cli([sys.executable, "-c", "import sys; sys.stdout.buffer.write('éééé'.encode('utf-8'))"])

        assert result.ok
        assert result.stdout == "éééé"
        assert not result.output_limit_exceeded

    async def test_stdout_overflow_kills_and_reaps_without_waiting_for_timeout(self, monkeypatch):
        monkeypatch.setattr(plan_quota_cli_runner, "MAX_CAPTURE_BYTES", 1024)
        script = (
            "import sys,time; "
            "sys.stderr.write('progress'); sys.stderr.flush(); "
            "sys.stdout.buffer.write(b'x' * 2048); sys.stdout.flush(); time.sleep(30)"
        )

        result = await asyncio.wait_for(
            run_cli([sys.executable, "-c", script], timeout=10),
            timeout=2,
        )

        assert not result.ok
        assert result.output_limit_exceeded
        assert result.output_limit_stream == "stdout"
        assert len(result.stdout.encode("utf-8")) == 1024
        assert result.stderr == "progress"
        assert not result.timed_out
        assert result.runtime_error == "output limit exceeded on stdout"

    async def test_stderr_overflow_is_bounded_and_typed(self, monkeypatch):
        monkeypatch.setattr(plan_quota_cli_runner, "MAX_CAPTURE_BYTES", 1024)
        script = "import sys; sys.stderr.buffer.write(b'e' * 1025); sys.stderr.flush()"

        result = await run_cli([sys.executable, "-c", script])

        assert not result.ok
        assert result.output_limit_exceeded
        assert result.output_limit_stream == "stderr"
        assert len(result.stderr.encode("utf-8")) == 1024

    async def test_output_limit_counts_raw_bytes_across_utf8_boundary(self, monkeypatch):
        monkeypatch.setattr(plan_quota_cli_runner, "MAX_CAPTURE_BYTES", 5)

        result = await run_cli([sys.executable, "-c", "import sys; sys.stdout.buffer.write('€€'.encode('utf-8'))"])

        assert result.output_limit_exceeded
        assert result.output_limit_stream == "stdout"
        assert result.stdout == "€�"

    async def test_output_overflow_does_not_wait_for_a_pipe_that_never_closes(self, monkeypatch):
        monkeypatch.setattr(plan_quota_cli_runner, "MAX_CAPTURE_BYTES", 4)
        monkeypatch.setattr(plan_quota_cli_runner, "_PROCESS_CLEANUP_TIMEOUT_S", 0.01)
        killed = asyncio.Event()

        class OverflowStream:
            def __init__(self):
                self.sent_overflow = False

            async def read(self, size):
                if not self.sent_overflow:
                    self.sent_overflow = True
                    return b"12345"
                await asyncio.Future()

        class HungStream:
            async def read(self, size):
                await asyncio.Future()

        class ProcessWithInheritedPipe:
            def __init__(self):
                self.returncode = None
                self.pid = 224
                self.stdin = None
                self.stdout = OverflowStream()
                self.stderr = HungStream()

            async def wait(self):
                await killed.wait()
                return self.returncode

            async def communicate(self, input_bytes=None):
                await killed.wait()
                return b"", b""

        process = ProcessWithInheritedPipe()

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            active_process.returncode = -9
            killed.set()

        monkeypatch.setattr(plan_quota_cli_runner.asyncio, "create_subprocess_exec", create_process)
        monkeypatch.setattr(plan_quota_cli_runner, "_kill_process_tree", kill_process_tree)

        result = await asyncio.wait_for(run_cli(["fake-plan-cli"], timeout=10), timeout=0.2)

        assert result.output_limit_exceeded
        assert result.output_limit_stream == "stdout"
        assert result.stdout == "1234"
        assert not result.timed_out

    async def test_pipe_failure_is_reported_without_waiting_for_process_timeout(self, monkeypatch):
        pipe_error = OSError("fixture pipe failure")
        killed = asyncio.Event()

        class FailingStream:
            async def read(self, size):
                raise pipe_error

        class HungStream:
            async def read(self, size):
                await asyncio.Future()

        class ProcessWithFailedPipe:
            def __init__(self):
                self.returncode = None
                self.pid = 225
                self.stdin = None
                self.stdout = FailingStream()
                self.stderr = HungStream()

            async def wait(self):
                await killed.wait()
                return self.returncode

            async def communicate(self, input_bytes=None):
                await killed.wait()
                return b"", b""

        process = ProcessWithFailedPipe()

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            active_process.returncode = -9
            killed.set()

        monkeypatch.setattr(plan_quota_cli_runner.asyncio, "create_subprocess_exec", create_process)
        monkeypatch.setattr(plan_quota_cli_runner, "_kill_process_tree", kill_process_tree)

        result = await asyncio.wait_for(run_cli(["fake-plan-cli"], timeout=10), timeout=0.2)

        assert result.runtime_error == "runner failed (OSError)"
        assert result.runtime_exception is pipe_error
        assert not result.timed_out

    async def test_overflow_kills_descendant_after_direct_child_exits(self, monkeypatch):
        monkeypatch.setattr(plan_quota_cli_runner, "MAX_CAPTURE_BYTES", 1024)
        descendant_code = (
            "import sys,time; time.sleep(1.0); sys.stdout.buffer.write(b'x' * 2048); sys.stdout.flush(); time.sleep(30)"
        )
        direct_child_code = (
            "import subprocess,sys; "
            f"p=subprocess.Popen([{sys.executable!r}, '-c', {descendant_code!r}], "
            "stdout=sys.stdout, stderr=sys.stderr); "
            "sys.stderr.write(f'CHILD_PID={p.pid}\\n'); sys.stderr.flush()"
        )
        descendant_pid: int | None = None

        try:
            result = await asyncio.wait_for(
                run_cli([sys.executable, "-c", direct_child_code], timeout=10),
                timeout=5,
            )
            match = re.search(r"CHILD_PID=(\d+)", result.stderr)
            assert match is not None
            descendant_pid = int(match.group(1))
            assert result.output_limit_exceeded
            assert result.returncode == 0
            for _ in range(100):
                if not _process_exists(descendant_pid):
                    break
                await asyncio.sleep(0.02)
            assert not _process_exists(descendant_pid)
        finally:
            if descendant_pid is not None and _process_exists(descendant_pid):
                _kill_test_process_tree(descendant_pid)

    async def test_successful_direct_child_cannot_leave_a_silent_descendant(self):
        descendant_code = "import time; time.sleep(30)"
        direct_child_code = (
            "import subprocess,sys; "
            f"p=subprocess.Popen([{sys.executable!r}, '-c', {descendant_code!r}], "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            "sys.stdout.write(f'CHILD_PID={p.pid}\\n'); sys.stdout.flush()"
        )
        descendant_pid: int | None = None

        try:
            result = await asyncio.wait_for(
                run_cli([sys.executable, "-c", direct_child_code], timeout=10),
                timeout=5,
            )
            match = re.search(r"CHILD_PID=(\d+)", result.stdout)
            assert match is not None
            descendant_pid = int(match.group(1))
            assert result.ok
            for _ in range(100):
                if not _process_exists(descendant_pid):
                    break
                await asyncio.sleep(0.02)
            assert not _process_exists(descendant_pid)
        finally:
            if descendant_pid is not None and _process_exists(descendant_pid):
                _kill_test_process_tree(descendant_pid)

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux child-subreaper containment")
    async def test_linux_supervisor_reaps_detached_session_descendant(self):
        script = (
            "import subprocess,sys; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], start_new_session=True); "
            "print(p.pid, flush=True)"
        )
        descendant_pid = None
        try:
            result = await run_cli([sys.executable, "-c", script], timeout=5)
            descendant_pid = int(result.stdout.strip())

            assert result.ok
            assert not _process_exists(descendant_pid)
        finally:
            if descendant_pid is not None and _process_exists(descendant_pid):
                _kill_test_process_tree(descendant_pid)

    async def test_overflow_drains_and_closes_real_subprocess_transports(self, monkeypatch):
        monkeypatch.setattr(plan_quota_cli_runner, "MAX_CAPTURE_BYTES", 64 * 1024)
        original_create = plan_quota_cli_runner.asyncio.create_subprocess_exec
        vendor_process = None

        async def capture_create(*args, **kwargs):
            nonlocal vendor_process
            process = await original_create(*args, **kwargs)
            if vendor_process is None and args and args[0] == sys.executable:
                vendor_process = process
            return process

        monkeypatch.setattr(plan_quota_cli_runner.asyncio, "create_subprocess_exec", capture_create)
        script = "import sys; block=b'x'*65536\nwhile True:\n sys.stdout.buffer.write(block); sys.stdout.buffer.flush()"

        result = await run_cli([sys.executable, "-c", script], timeout=10)

        assert result.output_limit_exceeded
        assert vendor_process is not None
        try:
            assert not vendor_process.stdout._buffer
            assert vendor_process.stdout._transport.is_closing()
            assert vendor_process._transport.is_closing()
        finally:
            vendor_process._transport.close()

    async def test_nonzero_exit_is_not_ok(self):
        result = await run_cli([sys.executable, "-c", "import sys; sys.exit(3)"])
        assert not result.ok
        assert result.returncode == 3
        assert not result.timed_out
        assert not result.launch_error

    async def test_communicate_error_uses_bounded_cleanup_and_preserves_error(
        self,
        monkeypatch,
    ):
        communicate_error = RuntimeError("fixture communicate failure")

        class ErrorThenHungProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 222
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    raise communicate_error
                await asyncio.Future()

            async def wait(self):
                await asyncio.Future()

        process = ErrorThenHungProcess()
        killed = []

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            killed.append(active_process)
            active_process.returncode = -9

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._PROCESS_CLEANUP_TIMEOUT_S",
            0.01,
        )

        result = await asyncio.wait_for(run_cli(["fake-plan-cli"]), timeout=0.2)

        assert result.runtime_failure_outcome == "cleanup_error"
        assert isinstance(result.runtime_exception, plan_quota_cli_runner.ProcessCleanupError)
        assert result.secondary_runtime_error == "runner failed (RuntimeError)"
        assert result.secondary_runtime_exception is communicate_error
        assert killed == [process]
        assert process.communicate_calls == 1

    async def test_timeout_kills_and_flags(self):
        result = await run_cli([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
        assert not result.ok
        assert result.timed_out
        assert result.returncode is None

    async def test_timeout_cleanup_never_rebuffers_output_and_closes_transport(self, monkeypatch):
        class Transport:
            def __init__(self):
                self.close_calls = 0

            def close(self):
                self.close_calls += 1

        class BlockingProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 404
                self.communicate_calls = 0
                self._transport = Transport()

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                await asyncio.Future()

            async def wait(self):
                return self.returncode

        process = BlockingProcess()

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            active_process.returncode = -9

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )

        result = await run_cli(["fake-plan-cli"], timeout=0.1)

        assert result.timed_out
        assert process.communicate_calls == 1
        assert process._transport.close_calls == 1

    async def test_timeout_cleanup_failure_is_the_primary_runtime_outcome(self, monkeypatch):
        cleanup_error = plan_quota_cli_runner.ProcessCleanupError("fixture cleanup failure")

        async def time_out(_process, _input_bytes):
            raise TimeoutError

        async def fail_cleanup(_process):
            return cleanup_error

        monkeypatch.setattr(plan_quota_cli_runner, "_communicate_bounded", time_out)
        monkeypatch.setattr(plan_quota_cli_runner, "_terminate_and_reap", fail_cleanup)

        result = await plan_quota_cli_runner._collect_started_process(
            object(),
            input_bytes=None,
            timeout=1,
            start=time.perf_counter(),
        )

        assert result.timed_out
        assert result.runtime_exception is cleanup_error
        assert result.runtime_failure_outcome == "cleanup_error"

    async def test_output_overflow_retains_limit_as_secondary_to_cleanup_failure(self, monkeypatch):
        cleanup_error = plan_quota_cli_runner.ProcessCleanupError("fixture cleanup failure")

        async def capture_with_cleanup_failure(_process, _input_bytes):
            return plan_quota_cli_runner._CapturedOutput(
                b"bounded",
                b"",
                plan_quota_cli_runner.OutputLimitStream.STDOUT,
                cleanup_error,
            )

        monkeypatch.setattr(plan_quota_cli_runner, "_communicate_bounded", capture_with_cleanup_failure)
        process = type("Process", (), {"returncode": -9})()

        result = await plan_quota_cli_runner._collect_started_process(
            process,
            input_bytes=None,
            timeout=1,
            start=time.perf_counter(),
        )

        assert result.output_limit_exceeded
        assert result.runtime_exception is cleanup_error
        assert result.runtime_failure_outcome == "cleanup_error"
        assert result.secondary_runtime_error == "output limit exceeded on stdout"

    async def test_cancellation_kills_started_process_and_propagates(self, monkeypatch):
        communicate_started = asyncio.Event()

        class BlockingProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 123
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    communicate_started.set()
                    await asyncio.Future()
                return b"", b""

        process = BlockingProcess()
        killed = []

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            killed.append(active_process)
            active_process.returncode = -9

        monkeypatch.setattr("deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec", create_process)
        monkeypatch.setattr("deepr.backends.plan_quota.cli_runner._kill_process_tree", kill_process_tree)
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-plan-cli")
        await communicate_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task

        assert killed == [process]
        assert process.communicate_calls == 1
        assert isinstance(
            exc_info.value.__dict__["plan_quota_cleanup_error"],
            plan_quota_cli_runner.ProcessCleanupError,
        )

    async def test_cancellation_during_launch_cleans_up_late_process_and_propagates(
        self,
        monkeypatch,
    ):
        launch_started = asyncio.Event()
        finish_launch = asyncio.Event()

        class LateProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 456
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                return b"", b""

        process = LateProcess()
        killed = []

        async def delayed_create(*args, **kwargs):
            launch_started.set()
            await finish_launch.wait()
            return process

        async def kill_process_tree(active_process):
            killed.append(active_process)
            active_process.returncode = -9

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            delayed_create,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-launch")
        await launch_started.wait()

        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish_launch.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert killed == [process]
        assert process.communicate_calls == 0

    async def test_hung_launch_cancellation_is_bounded_and_keeps_cleanup_owner(
        self,
        monkeypatch,
    ):
        from deepr.backends.plan_quota import cli_runner

        cli_runner._BACKGROUND_CLEANUP_FAILURES.clear()
        launch_started = asyncio.Event()
        finish_launch = asyncio.Event()
        cleanup_finished = asyncio.Event()

        class VeryLateProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 654
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                return b"", b""

        process = VeryLateProcess()

        async def hung_create(*args, **kwargs):
            launch_started.set()
            await finish_launch.wait()
            return process

        async def kill_process_tree(active_process):
            active_process.returncode = -9
            cleanup_finished.set()

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            hung_create,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._LAUNCH_CLEANUP_GRACE_S",
            0.01,
        )
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-hung-launch")
        await launch_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await asyncio.wait_for(task, timeout=0.2)

        assert isinstance(
            exc_info.value.__dict__["plan_quota_cleanup_error"],
            cli_runner.ProcessCleanupError,
        )
        assert "background ownership" in str(exc_info.value.__dict__["plan_quota_cleanup_error"])
        assert len(cli_runner._BACKGROUND_CLEANUPS) == 1
        finish_launch.set()
        await asyncio.wait_for(cleanup_finished.wait(), timeout=0.2)
        for _ in range(10):
            if not cli_runner._BACKGROUND_CLEANUPS:
                break
            await asyncio.sleep(0)

        assert cli_runner._BACKGROUND_CLEANUPS == set()
        assert isinstance(cli_runner._BACKGROUND_CLEANUP_FAILURES[-1], cli_runner.ProcessCleanupError)
        assert process.communicate_calls == 0

    async def test_cancellation_during_launch_timeout_grace_propagates(self, monkeypatch):
        from deepr.backends.plan_quota import cli_runner

        finish_launch = asyncio.Event()

        async def delayed_failure():
            await finish_launch.wait()
            raise OSError("fixture delayed launch failure")

        launch_task = asyncio.create_task(delayed_failure())
        monkeypatch.setattr(cli_runner, "_LAUNCH_CLEANUP_GRACE_S", 1.0)
        operation = asyncio.create_task(
            cli_runner._await_launch_task(
                launch_task,
                deadline=asyncio.get_running_loop().time() + 0.01,
                executable="plan-cli",
                start=time.perf_counter(),
                supervisor_control=None,
            )
        )
        await asyncio.sleep(0.03)

        operation.cancel()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await operation

        cleanup_error = exc_info.value.__dict__["plan_quota_cleanup_error"]
        assert isinstance(cleanup_error, cli_runner.ProcessCleanupError)
        assert "background ownership" in str(cleanup_error)
        finish_launch.set()
        with pytest.raises(OSError, match="delayed launch failure"):
            await asyncio.wait_for(launch_task, timeout=0.2)

    async def test_elapsed_launch_cleanup_preserves_cancellation_until_owned_cleanup_finishes(self, monkeypatch):
        cleanup_started = asyncio.Event()
        allow_cleanup = asyncio.Event()

        async def delayed_cleanup(_process):
            cleanup_started.set()
            await allow_cleanup.wait()
            return None

        monkeypatch.setattr(plan_quota_cli_runner, "_terminate_and_reap", delayed_cleanup)
        process = type("Process", (), {"returncode": None})()
        operation = asyncio.create_task(
            plan_quota_cli_runner._finish_elapsed_launch(
                process,
                "plan-cli",
                None,
                start=time.perf_counter(),
            )
        )
        await cleanup_started.wait()

        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done()
        allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await operation

    async def test_completed_process_release_finishes_before_cancellation_propagates(self, monkeypatch):
        release_started = asyncio.Event()
        allow_release = asyncio.Event()

        class Job:
            _handle = 127

            def __init__(self):
                self.closed = False

            def terminate(self):
                return True

            def close(self):
                self.closed = True
                self._handle = None
                return True

        class Process:
            returncode = 0

            def __init__(self):
                self._deepr_windows_kill_job = Job()

        process = Process()

        async def collect_result(*args, **kwargs):
            return plan_quota_cli_runner.CliResult(0, "answer", "", False, "", 1)

        async def delayed_release(active_process):
            release_started.set()
            await allow_release.wait()
            return plan_quota_cli_runner._terminate_windows_job(active_process)

        monkeypatch.setattr(plan_quota_cli_runner, "_collect_started_process", collect_result)
        monkeypatch.setattr(plan_quota_cli_runner, "_kill_process_tree", delayed_release)
        prepared = plan_quota_cli_runner._PreparedInvocation(
            ["plan-cli"],
            ["plan-cli"],
            "",
            None,
            None,
            False,
            None,
        )
        operation = asyncio.create_task(
            plan_quota_cli_runner._collect_owned_process(
                process,
                prepared,
                deadline=asyncio.get_running_loop().time() + 1,
                start=time.perf_counter(),
            )
        )
        await release_started.wait()

        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done()
        allow_release.set()
        with pytest.raises(asyncio.CancelledError):
            await operation

        assert process._deepr_windows_kill_job is None
        assert process.__dict__.get("_deepr_windows_kill_job") is None

    async def test_unexpected_late_launch_cleanup_failure_remains_typed(self):
        async def fail_cleanup():
            raise RuntimeError("fixture cleanup task failure")

        cleanup_task = asyncio.create_task(fail_cleanup())

        cleanup_error = await plan_quota_cli_runner._wait_for_launch_cleanup_grace(cleanup_task)

        assert isinstance(cleanup_error, plan_quota_cli_runner.ProcessCleanupError)
        assert str(cleanup_error) == "late process launch cleanup task failed"

    async def test_cancellation_cleanup_reap_is_bounded(self, monkeypatch):
        communicate_started = asyncio.Event()

        class HungReapProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 789
                self.communicate_calls = 0
                self.kill_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    communicate_started.set()
                await asyncio.Future()

            def kill(self):
                self.kill_calls += 1
                self.returncode = -9

        process = HungReapProcess()

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            active_process.kill()

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._PROCESS_CLEANUP_TIMEOUT_S",
            0.01,
        )
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-hung-reap")
        await communicate_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.2)

        assert process.kill_calls == 1
        assert process.communicate_calls == 1

    async def test_launch_failure_is_reported_not_raised(self):
        result = await run_cli(["deepr-no-such-binary-xyz-123"])
        assert not result.ok
        assert result.launch_error
        assert result.returncode is None

    def test_linux_supervisor_launch_marker_is_a_non_dispatch(self):
        from deepr.backends.plan_quota.posix_supervisor import LAUNCH_ERROR_STATUS

        class Supervisor:
            returncode = 125
            _deepr_posix_supervisor = True

        result = plan_quota_cli_runner.CliResult(125, "", "", False, "", 4)

        classified = plan_quota_cli_runner._classify_linux_supervisor_result(
            result,
            Supervisor(),
            executable="vendor-cli",
            supervisor_status=LAUNCH_ERROR_STATUS,
        )

        assert classified.returncode is None
        assert classified.launch_error
        assert classified.stderr == ""
        assert not classified.runtime_error

    def test_linux_supervisor_preserves_unmarked_vendor_exit_125(self):
        class Supervisor:
            returncode = 125
            _deepr_posix_supervisor = True

        result = plan_quota_cli_runner.CliResult(125, "", "vendor error", False, "", 4)

        classified = plan_quota_cli_runner._classify_linux_supervisor_result(
            result,
            Supervisor(),
            executable="vendor-cli",
            supervisor_status="vendor_exit",
        )

        assert classified is result

    def test_vendor_stderr_cannot_forge_supervisor_status(self):
        from deepr.backends.plan_quota.posix_supervisor import LAUNCH_ERROR_STATUS, VENDOR_EXIT_STATUS

        class Supervisor:
            returncode = 0
            _deepr_posix_supervisor = True

        result = plan_quota_cli_runner.CliResult(0, "", f"{LAUNCH_ERROR_STATUS}\n", False, "", 4)

        classified = plan_quota_cli_runner._classify_linux_supervisor_result(
            result,
            Supervisor(),
            executable="vendor-cli",
            supervisor_status=VENDOR_EXIT_STATUS,
        )

        assert classified is result
        assert classified.ok

    async def test_forced_linux_supervisor_kill_is_unconfirmed_cleanup(self, monkeypatch):
        class HungSupervisor:
            def __init__(self):
                self.returncode = None
                self.pid = 404
                self._deepr_posix_supervisor = True

            async def wait(self):
                if self.returncode is None:
                    await asyncio.Future()
                return self.returncode

            def kill(self):
                self.returncode = -9

        process = HungSupervisor()

        async def request_supervisor_shutdown(_process):
            return None

        monkeypatch.setattr(plan_quota_cli_runner, "_kill_process_tree", request_supervisor_shutdown)
        monkeypatch.setattr(plan_quota_cli_runner, "_PROCESS_CLEANUP_TIMEOUT_S", 0.01)

        error = await asyncio.wait_for(plan_quota_cli_runner._terminate_and_reap(process), timeout=0.2)

        assert isinstance(error, plan_quota_cli_runner.ProcessCleanupError)
        assert "deadline" in str(error)

    @pytest.mark.skipif(os.name != "nt", reason="Windows launches suspended before Job Object ownership")
    async def test_process_ownership_failure_aborts_before_vendor_code_runs(self, monkeypatch, tmp_path):
        marker = tmp_path / "vendor-ran.txt"
        ownership_error = OSError(5, "fixture ownership failure")

        def fail_ownership(_process):
            raise ownership_error

        monkeypatch.setattr(plan_quota_cli_runner, "_claim_process_ownership", fail_ownership)

        result = await asyncio.wait_for(
            run_cli(
                [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('vendor ran')",
                ]
            ),
            timeout=2,
        )

        assert not result.ok
        assert result.returncode is None
        assert result.stdout == ""
        assert "failed to launch" in result.launch_error
        assert result.launch_exception is ownership_error
        assert not marker.exists()

    async def test_launch_timeout_is_end_to_end_and_late_process_is_reaped(self, monkeypatch):
        launch_started = asyncio.Event()
        finish_launch = asyncio.Event()
        cleanup_finished = asyncio.Event()

        class LateProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 818

            async def wait(self):
                return self.returncode

        process = LateProcess()

        async def delayed_create(*args, **kwargs):
            launch_started.set()
            await finish_launch.wait()
            return process

        async def kill_process_tree(active_process):
            active_process.returncode = -9
            cleanup_finished.set()

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            delayed_create,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._LAUNCH_CLEANUP_GRACE_S",
            0.01,
        )

        started = time.perf_counter()
        result = await run_cli(["fake-plan-cli"], timeout=0.02)
        elapsed = time.perf_counter() - started

        assert result.timed_out
        assert result.runtime_failure_outcome == "cleanup_error"
        assert isinstance(result.cleanup_exception, plan_quota_cli_runner.ProcessCleanupError)
        assert "background ownership" in str(result.cleanup_exception)
        assert elapsed < 0.2
        assert launch_started.is_set()
        finish_launch.set()
        await asyncio.wait_for(cleanup_finished.wait(), timeout=0.2)

    async def test_finished_windows_job_close_failure_avoids_pid_reuse_fallback(self, monkeypatch):
        class FailingJob:
            def terminate(self):
                return True

            def close(self):
                return False

        class FinishedProcess:
            def __init__(self):
                self.returncode = 0
                self.pid = 919
                self._deepr_windows_kill_job = FailingJob()

        class Taskkill:
            returncode = 0

            async def wait(self):
                return 0

        calls = []

        async def create_taskkill(*args, **kwargs):
            calls.append(args)
            return Taskkill()

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.subprocess.CREATE_NEW_PROCESS_GROUP",
            1,
            raising=False,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_taskkill,
        )
        process = FinishedProcess()

        error = await _kill_process_tree(process)

        assert isinstance(error, plan_quota_cli_runner.ProcessCleanupError)
        assert calls == []
        assert process._deepr_windows_kill_job is not None

    async def test_successful_windows_job_cleanup_with_stale_returncode_avoids_taskkill(self, monkeypatch):
        class SuccessfulJob:
            def terminate(self):
                return True

            def close(self):
                return True

        class StaleProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 920
                self.kill_calls = 0
                self._deepr_windows_kill_job = SuccessfulJob()

            def kill(self):
                self.kill_calls += 1

        calls = []

        async def create_taskkill(*args, **kwargs):
            calls.append(args)
            raise AssertionError("stable Job Object ownership must not fall back to a PID")

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.subprocess.CREATE_NEW_PROCESS_GROUP",
            1,
            raising=False,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_taskkill,
        )
        process = StaleProcess()

        error = await _kill_process_tree(process)

        assert error is None
        assert calls == []
        assert process.kill_calls == 1
        assert process._deepr_windows_kill_job is None

    async def test_reentrant_windows_cleanup_never_falls_back_to_owned_pid(self, monkeypatch):
        class SuccessfulJob:
            def terminate(self):
                return True

            def close(self):
                return True

        class StaleProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 921
                self._deepr_windows_kill_job = SuccessfulJob()

            def kill(self):
                return None

        process = StaleProcess()

        assert await plan_quota_cli_runner._kill_windows_process_tree(process) is None
        assert await plan_quota_cli_runner._kill_windows_process_tree(process) is None

        assert process._deepr_windows_kill_job is None

    @pytest.mark.skipif(os.name != "nt", reason="Windows Job Object API")
    def test_windows_job_retains_handle_when_close_fails(self, monkeypatch):
        from deepr.backends.plan_quota import windows_job

        job = windows_job.WindowsKillJob(123)
        attempts = []

        def fail_close(handle):
            attempts.append(handle)
            return False

        monkeypatch.setattr(windows_job, "_close_handle", fail_close)

        assert job.close() is False
        assert job._handle == 123
        assert attempts == [123, 123, 123]

    @pytest.mark.skipif(os.name != "nt", reason="Windows Job Object API")
    def test_windows_job_close_exception_retains_process_global_owner(self, monkeypatch):
        from deepr.backends.plan_quota import windows_job

        class RaisingJob:
            _handle = 126

            def close(self):
                raise OSError("fixture close failure")

        class Process:
            _deepr_windows_kill_job = RaisingJob()

        retained = []
        monkeypatch.setattr(windows_job, "retain_failed_job", retained.append)

        error = plan_quota_cli_runner._close_windows_job(Process())

        assert isinstance(error, plan_quota_cli_runner.ProcessCleanupError)
        assert retained == [Process._deepr_windows_kill_job]

    @pytest.mark.skipif(os.name != "nt", reason="Windows Job Object API")
    def test_windows_retained_job_is_removed_after_successful_retry(self, monkeypatch):
        from deepr.backends.plan_quota import windows_job

        class RetryJob:
            _handle = 123

            def __init__(self):
                self.calls = []

            def terminate(self):
                self.calls.append("terminate")
                return True

            def close(self):
                self.calls.append("close")
                self._handle = None
                return True

        monkeypatch.setattr(windows_job, "_RETAINED_KILL_JOBS", {})
        job = RetryJob()
        windows_job.retain_failed_job(job)

        windows_job.retry_retained_jobs()

        assert job.calls == ["terminate", "close"]
        assert windows_job._RETAINED_KILL_JOBS == {}

    @pytest.mark.skipif(os.name != "nt", reason="Windows Job Object API")
    def test_unresolved_windows_job_blocks_next_process_ownership(self, monkeypatch):
        from deepr.backends.plan_quota import windows_job

        class UnresolvedJob:
            _handle = 124

            def terminate(self):
                return False

            def close(self):
                return False

        create_calls = []
        monkeypatch.setattr(windows_job, "_RETAINED_KILL_JOBS", {})
        monkeypatch.setattr(windows_job, "_create_kill_job", lambda: create_calls.append(True))
        windows_job.retain_failed_job(UnresolvedJob())

        with pytest.raises(windows_job.WindowsProcessOwnershipError, match="cleanup remains unresolved"):
            windows_job.attach_kill_job_and_resume(1234)

        assert create_calls == []
        assert len(windows_job._RETAINED_KILL_JOBS) == 1

    @pytest.mark.skipif(os.name != "nt", reason="Windows Job Object API")
    def test_retained_windows_job_retries_are_serialized(self, monkeypatch):
        from deepr.backends.plan_quota import windows_job

        close_started = threading.Event()
        allow_close = threading.Event()
        second_finished = threading.Event()

        class BlockingJob:
            _handle = 125

            def terminate(self):
                return True

            def close(self):
                close_started.set()
                assert allow_close.wait(timeout=2)
                self._handle = None
                return True

        monkeypatch.setattr(windows_job, "_RETAINED_KILL_JOBS", {})
        windows_job.retain_failed_job(BlockingJob())
        first = threading.Thread(target=windows_job.retry_retained_jobs)
        second = threading.Thread(target=lambda: (windows_job.retry_retained_jobs(), second_finished.set()))
        first.start()
        assert close_started.wait(timeout=2)
        second.start()

        assert not second_finished.wait(timeout=0.05)
        allow_close.set()
        first.join(timeout=2)
        second.join(timeout=2)

        assert second_finished.is_set()
        assert not first.is_alive()
        assert not second.is_alive()

    @pytest.mark.skipif(os.name != "nt", reason="Windows Job Object API")
    def test_windows_ownership_rollback_preserves_primary_and_retains_handle(self, monkeypatch):
        from deepr.backends.plan_quota import windows_job

        primary_error = windows_job.WindowsProcessOwnershipError(5, "fixture open failure")
        retained = []

        def fail_open(_pid):
            raise primary_error

        def fail_terminate(_job):
            raise OSError("fixture terminate failure")

        def fail_close(_job):
            raise OSError("fixture close failure")

        monkeypatch.setattr(windows_job, "_create_kill_job", lambda: 128)
        monkeypatch.setattr(windows_job, "_open_process", fail_open)
        monkeypatch.setattr(windows_job.WindowsKillJob, "terminate", fail_terminate)
        monkeypatch.setattr(windows_job.WindowsKillJob, "close", fail_close)
        monkeypatch.setattr(windows_job, "retain_failed_job", retained.append)

        with pytest.raises(windows_job.WindowsProcessOwnershipError) as exc_info:
            windows_job.attach_kill_job_and_resume(1234)

        assert exc_info.value is primary_error
        assert len(retained) == 1
        assert retained[0]._handle == 128

    @pytest.mark.skipif(os.name != "nt", reason="Windows Job Object API")
    def test_windows_job_configuration_rollback_retains_handle_on_close_exception(self, monkeypatch):
        from deepr.backends.plan_quota import windows_job

        retained = []

        def fail_terminate(_job):
            raise OSError("fixture terminate failure")

        def fail_close(_job):
            raise OSError("fixture close failure")

        monkeypatch.setattr(windows_job._kernel32, "CreateJobObjectW", lambda *_args: 129)
        monkeypatch.setattr(windows_job._kernel32, "SetInformationJobObject", lambda *_args: 0)
        monkeypatch.setattr(windows_job.WindowsKillJob, "terminate", fail_terminate)
        monkeypatch.setattr(windows_job.WindowsKillJob, "close", fail_close)
        monkeypatch.setattr(windows_job, "retain_failed_job", retained.append)

        with pytest.raises(windows_job.WindowsProcessOwnershipError, match="SetInformationJobObject"):
            windows_job._create_kill_job()

        assert len(retained) == 1
        assert retained[0]._handle == 129

    async def test_ownership_failure_preserves_unowned_cleanup_uncertainty(self, monkeypatch):
        ownership_error = OSError("fixture ownership failure")
        cleanup_error = plan_quota_cli_runner.ProcessCleanupError("fixture unowned reap failure")

        class SuspendedProcess:
            returncode = None

        async def create_process(*args, **kwargs):
            return SuspendedProcess()

        def fail_ownership(_process):
            raise ownership_error

        async def fail_cleanup(_process):
            return cleanup_error

        monkeypatch.setattr(plan_quota_cli_runner.asyncio, "create_subprocess_exec", create_process)
        monkeypatch.setattr(plan_quota_cli_runner, "_claim_process_ownership", fail_ownership)
        monkeypatch.setattr(plan_quota_cli_runner, "_abort_unowned_process", fail_cleanup)

        result = await run_cli(["fake-plan-cli"])

        assert result.launch_exception is ownership_error
        assert result.cleanup_exception is cleanup_error
        assert result.cleanup_error == "runner failed (ProcessCleanupError)"

    async def test_cancellation_waits_for_unowned_suspended_process_cleanup(self, monkeypatch):
        cleanup_started = asyncio.Event()
        allow_cleanup = asyncio.Event()

        class SuspendedProcess:
            returncode = None

        async def create_process(*args, **kwargs):
            return SuspendedProcess()

        def fail_ownership(_process):
            raise OSError("fixture ownership failure")

        async def delayed_cleanup(_process):
            cleanup_started.set()
            await allow_cleanup.wait()
            return None

        monkeypatch.setattr(plan_quota_cli_runner.asyncio, "create_subprocess_exec", create_process)
        monkeypatch.setattr(plan_quota_cli_runner, "_claim_process_ownership", fail_ownership)
        monkeypatch.setattr(plan_quota_cli_runner, "_abort_unowned_process", delayed_cleanup)
        operation = asyncio.create_task(run_cli(["fake-plan-cli"]))
        await cleanup_started.wait()

        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done()
        allow_cleanup.set()

        with pytest.raises(asyncio.CancelledError):
            await operation

    async def test_launch_failure_hides_resolved_path_and_retains_raw_exception(
        self,
        monkeypatch,
    ):
        launch_exception = FileNotFoundError(
            2,
            "private operating system detail",
            "C:/Users/private-account/bin/codex.exe",
        )

        async def fail_launch(*args, **kwargs):
            raise launch_exception

        monkeypatch.setattr(
            "deepr.backends.plan_quota.process_launch.shutil.which",
            lambda _exe: "C:/Users/private-account/bin/codex.exe",
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            fail_launch,
        )

        result = await run_cli(["codex"])

        assert "C:/Users" not in result.launch_error
        assert "private-account" not in result.launch_error
        assert "private operating system detail" not in result.launch_error
        assert result.launch_error == "failed to launch 'codex.exe' (FileNotFoundError, errno=2)"
        assert result.launch_exception is launch_exception
        assert "private-account" not in repr(result)

    @pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf"), "1"])
    async def test_invalid_timeout_is_rejected_before_launch(self, monkeypatch, timeout):
        launch_calls = []

        async def create_process(*args, **kwargs):
            launch_calls.append(args)
            raise AssertionError("must not launch")

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )

        with pytest.raises(ValueError, match="finite positive"):
            await run_cli(["fake-plan-cli"], timeout=timeout)

        assert launch_calls == []

    async def test_scratch_failure_is_structured_and_path_safe_before_launch(self, monkeypatch):
        launch_calls = []
        scratch_error = PermissionError("C:/Users/private-account/scratch")

        async def create_process(*args, **kwargs):
            launch_calls.append(args)
            raise AssertionError("must not launch")

        def fail_scratch():
            raise scratch_error

        monkeypatch.setattr("deepr.backends.plan_quota.cli_runner._scratch_dir", fail_scratch)
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )

        result = await run_cli(["fake-plan-cli"])

        assert result.launch_error == "failed to launch 'fake-plan-cli' (PermissionError)"
        assert "private-account" not in result.launch_error
        assert result.launch_exception is scratch_error
        assert launch_calls == []

    async def test_invalid_stdin_is_rejected_before_process_launch(self, monkeypatch):
        launch_calls = []

        async def create_process(*args, **kwargs):
            launch_calls.append(args)
            raise AssertionError("must not launch")

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )

        result = await run_cli(["fake-plan-cli"], stdin="unpaired-\ud800")

        assert "UnicodeEncodeError" in result.launch_error
        assert result.returncode is None
        assert launch_calls == []

    async def test_null_bytes_in_prompt_argument_are_normalized(self):
        result = await run_cli([sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", "fresh\x00context"])
        assert result.ok
        assert result.stdout == "fresh context"

    def test_executable_is_resolved_with_pathext(self, monkeypatch):
        monkeypatch.setattr(
            "deepr.backends.plan_quota.process_launch.shutil.which",
            lambda exe: "C:/bin/codex.cmd" if exe == "codex" else None,
        )

        assert _clean_argv(["codex", "exec"]) == ["C:/bin/codex.cmd", "exec"]

    def test_non_linux_posix_launch_fails_closed_without_tree_ownership(self, monkeypatch):
        from deepr.backends.plan_quota import process_launch

        monkeypatch.setattr(process_launch.os, "name", "posix")
        monkeypatch.setattr(process_launch.sys, "platform", "darwin")

        with pytest.raises(RuntimeError, match="process-tree ownership is unavailable"):
            process_launch.owned_process_argv(["plan-cli"])

    async def test_invalid_environment_entries_are_omitted(self):
        env: dict[str, object] = dict(os.environ)
        env["DEEPR_BAD"] = "x\x00y"
        env["DEEPR_NONE"] = None
        result = await run_cli(
            [
                sys.executable,
                "-c",
                (
                    "import json, os; "
                    "print(json.dumps({'bad': os.environ.get('DEEPR_BAD'), "
                    "'none': os.environ.get('DEEPR_NONE')}, sort_keys=True))"
                ),
            ],
            env=env,
        )
        assert result.ok
        assert json.loads(result.stdout) == {"bad": None, "none": None}
