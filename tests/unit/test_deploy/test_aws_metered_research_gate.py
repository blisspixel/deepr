"""Regression tests for the v2.36 AWS metered-research boundary."""

from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
API_HANDLER = REPO_ROOT / "deploy" / "aws" / "src" / "api" / "handler.py"
WORKER = REPO_ROOT / "deploy" / "aws" / "src" / "worker" / "worker.py"
AWS_VALIDATE = REPO_ROOT / "deploy" / "aws" / "validate.sh"
DEPLOY_README = REPO_ROOT / "deploy" / "README.md"
BLOCK_CODE = "aws_metered_research_accounting_unavailable"


class _Boto3Stub(ModuleType):
    def __init__(self) -> None:
        super().__init__("boto3")
        self.clients: dict[str, MagicMock] = {}
        self.resources: dict[str, MagicMock] = {}

    def client(self, name: str) -> MagicMock:
        return self.clients.setdefault(name, MagicMock(name=f"{name}_client"))

    def resource(self, name: str) -> MagicMock:
        return self.resources.setdefault(name, MagicMock(name=f"{name}_resource"))


class _ClientError(Exception):
    """Minimal botocore ClientError stand-in for dependency-free module loading."""


def _load(path: Path, name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setitem(sys.modules, "boto3", _Boto3Stub())
    botocore = ModuleType("botocore")
    exceptions = ModuleType("botocore.exceptions")
    exceptions.ClientError = _ClientError  # type: ignore[attr-defined]
    botocore.exceptions = exceptions  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_rejects_submission_before_parsing_or_durable_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _load(API_HANDLER, "deepr_aws_api_gate_test", monkeypatch)
    api.jobs_table = MagicMock()
    api.sqs = MagicMock()
    monkeypatch.setattr(api, "validate_api_key", lambda _event: True)
    monkeypatch.setattr(api.json, "loads", MagicMock(side_effect=AssertionError("request body was parsed")))
    monkeypatch.setattr(api.uuid, "uuid4", MagicMock(side_effect=AssertionError("job id was allocated")))

    result = api.lambda_handler(
        {"httpMethod": "POST", "path": "/jobs", "headers": {}, "body": "private prompt"},
        None,
    )
    payload = json.JSONDecoder().decode(result["body"])

    assert result["statusCode"] == 503
    assert payload == {
        "error": api.AWS_METERED_RESEARCH_BLOCK_MESSAGE,
        "error_code": BLOCK_CODE,
        "status": "blocked",
        "retryable": False,
        "provider_work_started": False,
        "durable_job_written": False,
        "queue_message_written": False,
    }
    assert "private prompt" not in result["body"]
    api.jobs_table.put_item.assert_not_called()
    api.sqs.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_worker_direct_execution_blocks_before_provider_import(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _load(WORKER, "deepr_aws_worker_direct_gate_test", monkeypatch)
    imported_provider = False
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        nonlocal imported_provider
        if name.startswith("deepr.providers"):
            imported_provider = True
            raise AssertionError("provider module imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    with pytest.raises(worker.AWSMeteredResearchDisabledError) as raised:
        await worker.execute_research({"id": "job-1", "prompt": "private prompt"})

    assert raised.value.code == BLOCK_CODE
    assert raised.value.provider_work_started is False
    assert imported_provider is False


@pytest.mark.asyncio
async def test_worker_acknowledges_legacy_message_without_provider_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _load(WORKER, "deepr_aws_worker_message_gate_test", monkeypatch)
    updates = MagicMock()
    execute = AsyncMock(side_effect=AssertionError("provider execution reached"))
    save = MagicMock(side_effect=AssertionError("result write reached"))
    monkeypatch.setattr(worker, "is_job_cancelled", lambda _job_id: False)
    monkeypatch.setattr(worker, "update_job_status", updates)
    monkeypatch.setattr(worker, "execute_research", execute)
    monkeypatch.setattr(worker, "save_result", save)

    success = await worker.process_message(
        {"Body": json.dumps({"id": "legacy-job", "prompt": "private prompt", "model": "private-model"})}
    )

    assert success is True
    updates.assert_called_once_with(
        "legacy-job",
        "failed",
        error=worker.AWS_METERED_RESEARCH_BLOCK_MESSAGE,
        error_code=BLOCK_CODE,
        retryable=False,
        provider_work_started=False,
    )
    execute.assert_not_awaited()
    save.assert_not_called()
    assert "private prompt" not in str(updates.call_args)
    assert "private-model" not in str(updates.call_args)


def test_api_and_worker_publish_the_same_dependency_local_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _load(API_HANDLER, "deepr_aws_api_contract_test", monkeypatch)
    worker = _load(WORKER, "deepr_aws_worker_contract_test", monkeypatch)

    assert api.AWS_METERED_RESEARCH_EXECUTION_ENABLED is False
    assert worker.AWS_METERED_RESEARCH_EXECUTION_ENABLED is False
    assert api.AWS_METERED_RESEARCH_BLOCK_CODE == worker.AWS_METERED_RESEARCH_BLOCK_CODE == BLOCK_CODE
    assert api.AWS_METERED_RESEARCH_BLOCK_MESSAGE == worker.AWS_METERED_RESEARCH_BLOCK_MESSAGE


def test_aws_validation_proves_the_gate_without_enqueuing_a_job() -> None:
    script = AWS_VALIDATE.read_text(encoding="utf-8")

    assert BLOCK_CODE in script
    assert "POST /jobs returns the v2.36 accounting gate" in script
    assert "JOB_ID=" not in script
    assert "GET /jobs/{id}" not in script
    assert "grok-" not in script


def test_deploy_guide_does_not_publish_stale_aws_model_allowlist() -> None:
    guide = DEPLOY_README.read_text(encoding="utf-8")

    assert BLOCK_CODE in guide
    assert "No model identifier is valid for AWS execution in v2.36" in guide
    for stale_model in (
        "gemini-2.0-flash-thinking-exp",
        "gemini-2.5-pro-exp-03-25",
        "grok-3-mini-fast",
        "grok-3-fast",
    ):
        assert stale_model not in guide
