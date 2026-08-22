"""Static security contracts for legacy hosted research deployment shards."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _function(relative: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(_source(relative))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _shared_security_module():
    path = REPO_ROOT / "deploy/shared/deepr_api_common/security.py"
    spec = importlib.util.spec_from_file_location("test_deepr_api_common_security", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_env_loader_never_evaluates_values() -> None:
    loader = _source("deploy/shared/load-env.sh")
    assert "eval" not in loader
    assert "xargs" not in loader
    assert "export $(" not in loader


def test_legacy_cloud_deploy_scripts_fail_closed_before_any_cli() -> None:
    forbidden = (
        "sam build",
        "sam deploy",
        "az group create",
        "az deployment",
        "gcloud config",
        "terraform init",
        "terraform apply",
        "subprocess",
    )
    for cloud in ("aws", "azure", "gcp"):
        for script_name in ("deploy.sh", "destroy.sh", "validate.sh"):
            script = _source(f"deploy/{cloud}/{script_name}")
            assert "cannot enforce the operator's total dollar ceiling" in script
            assert "exit 2" in script
            assert all(command not in script for command in forbidden)


def test_legacy_azure_setup_fails_closed_without_cloud_or_file_operations() -> None:
    source = _source("scripts/setup_azure.py")
    assert "cannot enforce the operator's total dollar ceiling" in source
    assert "return 2" in source
    assert all(
        command not in source
        for command in ("subprocess", "az group", "storage account create", "servicebus", "write_text", "input(")
    )


def test_cloud_api_key_validators_fail_closed_when_secret_is_missing() -> None:
    validate_api_key_from_headers = _shared_security_module().validate_api_key_from_headers

    assert validate_api_key_from_headers("Bearer secret", "secret", "") is False
    assert validate_api_key_from_headers(None, None, "") is False
    assert validate_api_key_from_headers("Bearer secret", None, "secret") is True
    assert validate_api_key_from_headers(123, object(), "secret") is False
    assert validate_api_key_from_headers("Bearer 123", None, 123) is False
    for relative in (
        "deploy/azure/functions/function_app.py",
        "deploy/gcp/functions/main.py",
        "deploy/aws/src/api/handler.py",
    ):
        source = _source(relative)
        assert "allow all" not in source
        function_source = ast.get_source_segment(source, _function(relative, "validate_api_key")) or ""
        assert "compare_digest" in function_source
        assert "isinstance" in function_source
        assert "return False" in function_source
    azure_loader = (
        ast.get_source_segment(
            source := _source("deploy/azure/functions/function_app.py"),
            _function("deploy/azure/functions/function_app.py", "get_api_key"),
        )
        or ""
    )
    assert '_api_key_cache = ""' not in azure_loader
    assert "raise RuntimeError" in azure_loader


def test_azure_and_gcp_submission_gates_precede_payload_and_queue_work() -> None:
    cases = [
        ("deploy/azure/functions/function_app.py", "AZURE_METERED_RESEARCH_EXECUTION_ENABLED"),
        ("deploy/gcp/functions/main.py", "GCP_METERED_RESEARCH_EXECUTION_ENABLED"),
    ]
    for relative, gate_name in cases:
        source = _source(relative)
        function = _function(relative, "submit_job")
        function_source = ast.get_source_segment(source, function) or ""
        assert f"{gate_name} = False" in source
        assert function_source.index(f"if not {gate_name}") < function_source.index("get_json")
        assert "provider_work_started" in function_source
        assert "durable_job_written" in function_source
        assert "queue_message_written" in function_source
