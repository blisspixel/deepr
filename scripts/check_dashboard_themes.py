"""Capture both production dashboard themes against isolated zero-cost demo state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "src/deepr/web/frontend"
_SAFE_ENVIRONMENT = {
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
}
_SERVER = r"""
import json, os, sys
from pathlib import Path
runtime = Path(os.environ['DEEPR_DATA_DIR']).parent.resolve()
def local_only(event, args):
    if event == 'socket.connect':
        with (runtime.parent / 'network-attempts.txt').open('a', encoding='utf-8') as target:
            target.write('socket.connect refused\n')
        raise RuntimeError('Outgoing connection refused by dashboard QA')
sys.addaudithook(local_only)
from deepr.config import load_config
config = load_config()
roots = {key: config[key] for key in ['queue_db_path', 'results_dir', 'experts_dir']}
assert all(Path(value).resolve().is_relative_to(runtime) for value in roots.values())
assert config['max_monthly_cost'] == 0
(runtime.parent / 'canonical-roots.json').write_text(json.dumps(roots, indent=2) + '\n', encoding='utf-8')
from deepr.web import demo_seed
# Synthetic zero-cost jobs are selected before canonical seed writes. Never
# erase positive history or grant account/wallet authority to satisfy a capture.
demo_seed.SAMPLE_JOBS = [{**row, 'cost': 0.0} for row in demo_seed.SAMPLE_JOBS]
from deepr.web.app import app, _run_loopback_development_server
@app.after_request
def identify_fixture(response):
    response.headers['X-Deepr-QA-Instance'] = os.environ['DEEPR_QA_INSTANCE']
    return response
_run_loopback_development_server(host='127.0.0.1', port=int(sys.argv[1]), debug=False)
"""


def _environment(output: Path, inherited: dict[str, str], instance: str) -> dict[str, str]:
    """Bind every runtime path before imports and inherit no credential or QA override."""
    runtime = output / "runtime"
    environment = {key: value for key, value in inherited.items() if key in _SAFE_ENVIRONMENT}
    environment.update(
        {
            "PYTHON_DOTENV_DISABLED": "1",
            "DEEPR_ENV_FILE": str(runtime / "absent.env"),
            "DEEPR_DATA_DIR": str(runtime / "data"),
            "DEEPR_EXPERTS_PATH": str(runtime / "experts"),
            "DEEPR_REPORTS_PATH": str(runtime / "reports"),
            "DEEPR_COST_DATA_DIR": str(runtime / "costs"),
            "DEEPR_QUEUE_DB_PATH": str(runtime / "queue.db"),
            "DEEPR_BUDGET_FILE": str(runtime / "budget.json"),
            "DEEPR_DEMO": "1",
            "DEEPR_WEB_ALLOW_UNAUTHENTICATED_LOOPBACK": "1",
            "DEEPR_QA_INSTANCE": instance,
        }
    )
    for window in ("JOB", "DAY", "WEEK", "MONTH"):
        environment[f"DEEPR_MAX_COST_PER_{window}"] = "0"
    return environment


def _stop(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _read_json(url: str, *, instance: str) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=3) as response:
        if response.headers.get("X-Deepr-QA-Instance") != instance:
            raise RuntimeError("Response is not from this isolated QA backend")
        return json.load(response)


def _ready(base: str, process: subprocess.Popen[Any], instance: str) -> None:
    deadline = time.monotonic() + 60
    while True:
        if process.poll() is not None:
            raise RuntimeError("Dashboard backend exited; see backend.log")
        try:
            if _read_json(base + "/api/health", instance=instance).get("status") == "healthy":
                return
        except (OSError, urllib.error.URLError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("Dashboard backend readiness timed out")
        time.sleep(0.25)


def check(output: Path, node: str) -> None:
    """Never reuse operator state; always stop only the process this helper starts."""
    if not (FRONTEND / "dist/index.html").is_file():
        raise RuntimeError("Production frontend is missing; run the pinned npm build first")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "runtime").mkdir()
    working = output / "working"
    working.mkdir()
    instance = uuid.uuid4().hex
    environment = _environment(output, dict(os.environ), instance)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    receipt: dict[str, Any] = {
        "synthetic_demo": True,
        "seed_variant": "Zero-cost jobs before canonical seeding",
        "base": base,
        "monthly_ceiling": 0,
        "themes": [],
        "accepted": False,
    }
    try:
        with (output / "backend.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                [sys.executable, "-c", _SERVER, str(port)],
                cwd=working,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                _ready(base, server, instance)
                cost = _read_json(base + "/api/cost/summary", instance=instance)
                summary = cost["summary"]
                assert summary["paid_api_frozen"] and summary["monthly_limit"] == 0 and summary["total"] == 0
                (output / "cost-before.json").write_text(json.dumps(cost, indent=2) + "\n", encoding="utf-8")
                for theme in ("light", "dark"):
                    with (output / f"{theme}-qa.log").open("w", encoding="utf-8") as qa_log:
                        subprocess.run(
                            [node, str(FRONTEND / "screenshot-qa.mjs")],
                            cwd=FRONTEND,
                            env={
                                **environment,
                                "QA_BASE": base,
                                "QA_API": base,
                                "QA_THEME": theme,
                                "QA_OUTPUT": str(output / "captures"),
                                "QA_DEMO": "0",
                            },
                            stdout=qa_log,
                            stderr=subprocess.STDOUT,
                            timeout=240,
                            check=True,
                        )
                    observed = json.loads((output / "captures" / theme / "receipt.json").read_text(encoding="utf-8"))
                    assert len(observed["captures"]) == 12 and all(
                        not values for values in observed["observations"].values()
                    )
                    receipt["themes"].append(theme)
                after = _read_json(base + "/api/cost/summary", instance=instance)
                assert after["summary"]["total"] == 0 and after["summary"]["paid_api_frozen"]
                ledger = output / "runtime/costs/cost_ledger.jsonl"
                events = (
                    [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
                    if ledger.exists()
                    else []
                )
                assert all(event["cost_usd"] == 0 for event in events)
                assert not (output / "network-attempts.txt").exists()
                receipt.update(
                    accepted=True,
                    ledger_events=len(events),
                    outgoing_connection_attempts=0,
                    screenshots={
                        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted((output / "captures").rglob("*.png"))
                    },
                )
            finally:
                _stop(server)
                receipt["backend_stopped"] = server.poll() is not None
    finally:
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".agent/dashboard-theme-qa")
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    if not args.node:
        parser.error("Node is required; use the version pinned in CI")
    check(args.output, args.node)
    print("Production dashboard light/dark captures accepted at $0.")


if __name__ == "__main__":
    main()
