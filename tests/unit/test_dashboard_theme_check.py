"""Isolation and failure cleanup for actual production dashboard captures."""

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_dashboard_themes.py"
spec = importlib.util.spec_from_file_location("dashboard_theme_check", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_capture_environment_binds_private_roots_and_drops_credentials_and_overrides(tmp_path):
    inherited = {
        "PATH": "fixture",
        "OPENAI_API_KEY": "not-a-key",
        "GH_TOKEN": "not-a-token",
        "QA_ALLOW_OVER_LIMIT_COST_SCREENSHOT": "1",
        "QA_DEMO": "1",
        "DEEPR_DATA_DIR": "operator-state",
    }
    env = checker._environment(tmp_path, inherited, "fixture")
    assert "OPENAI_API_KEY" not in env and "GH_TOKEN" not in env
    assert "QA_ALLOW_OVER_LIMIT_COST_SCREENSHOT" not in env and "QA_DEMO" not in env
    assert env["PYTHON_DOTENV_DISABLED"] == "1"
    for key in (
        "DEEPR_DATA_DIR",
        "DEEPR_EXPERTS_PATH",
        "DEEPR_REPORTS_PATH",
        "DEEPR_COST_DATA_DIR",
        "DEEPR_QUEUE_DB_PATH",
        "DEEPR_BUDGET_FILE",
    ):
        assert Path(env[key]).is_relative_to(tmp_path)
    assert all(env[f"DEEPR_MAX_COST_PER_{window}"] == "0" for window in ("JOB", "DAY", "WEEK", "MONTH"))


def test_existing_capture_output_is_refused_before_server_or_seed(monkeypatch, tmp_path):
    frontend = tmp_path / "frontend"
    (frontend / "dist").mkdir(parents=True)
    (frontend / "dist/index.html").write_text("fixture")
    monkeypatch.setattr(checker, "FRONTEND", frontend)
    output = tmp_path / "operator-state"
    output.mkdir()
    marker = output / "retained.txt"
    marker.write_text("must survive")
    launch = MagicMock(side_effect=AssertionError("Must not launch"))
    monkeypatch.setattr(checker.subprocess, "Popen", launch)
    with pytest.raises(FileExistsError):
        checker.check(output, "node")
    assert marker.read_text() == "must survive"
    launch.assert_not_called()


def test_missing_build_is_refused_before_creating_output(monkeypatch, tmp_path):
    monkeypatch.setattr(checker, "FRONTEND", tmp_path / "missing")
    output = tmp_path / "output"
    with pytest.raises(RuntimeError, match="Production frontend is missing"):
        checker.check(output, "node")
    assert not output.exists()


def test_cleanup_terminates_own_server_and_escalates_a_timeout():
    process = MagicMock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("fixture", 10), 0]
    checker._stop(process)
    assert process.method_calls == [
        call.poll(),
        call.terminate(),
        call.wait(timeout=10),
        call.kill(),
        call.wait(timeout=5),
    ]


def test_spa_http_success_does_not_satisfy_backend_health(monkeypatch):
    process = MagicMock()
    process.poll.return_value = None
    urls = []

    def unhealthy(url, **_):
        urls.append(url)
        return {"status": "not healthy"}

    monkeypatch.setattr(checker, "_read_json", unhealthy)
    ticks = iter([0, 61])
    monkeypatch.setattr(checker.time, "monotonic", lambda: next(ticks))
    with pytest.raises(RuntimeError, match="readiness timed out"):
        checker._ready("http://127.0.0.1:1234", process, "fixture")
    assert urls == ["http://127.0.0.1:1234/api/health"]


def test_readiness_failure_still_stops_the_started_server(monkeypatch, tmp_path):
    frontend = tmp_path / "frontend"
    (frontend / "dist").mkdir(parents=True)
    (frontend / "dist/index.html").write_text("fixture")
    monkeypatch.setattr(checker, "FRONTEND", frontend)
    process = MagicMock()
    process.poll.return_value = 0
    monkeypatch.setattr(checker.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(checker, "_ready", MagicMock(side_effect=RuntimeError("fixture readiness failure")))
    stop = MagicMock()
    monkeypatch.setattr(checker, "_stop", stop)
    with pytest.raises(RuntimeError, match="fixture readiness failure"):
        checker.check(tmp_path / "capture", "node")
    stop.assert_called_once_with(process)
    assert (tmp_path / "capture/receipt.json").is_file()


def test_health_reads_connect_directly_even_with_caller_proxy_environment(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    visits = {"healthy": [], "proxy": []}

    def handler(kind):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                visits[kind].append(self.path)
                payload = json.dumps({"status": kind}).encode()
                self.send_response(200)
                self.send_header("X-Deepr-QA-Instance", "fixture")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_):
                pass

        return Handler

    servers = [ThreadingHTTPServer(("127.0.0.1", 0), handler(kind)) for kind in visits]
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    try:
        proxy = f"http://127.0.0.1:{servers[1].server_port}"
        for key in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
            monkeypatch.setenv(key, proxy)
        for key in ("no_proxy", "NO_PROXY"):
            monkeypatch.setenv(key, "")
        result = checker._read_json(f"http://127.0.0.1:{servers[0].server_port}/api/health", instance="fixture")
        assert result == {"status": "healthy"}
        assert visits == {"healthy": ["/api/health"], "proxy": []}
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
            assert not thread.is_alive()
