"""Static security contracts for legacy hosted research deployment shards."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _function(relative: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(_source(relative))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_env_loader_never_evaluates_or_places_values_in_child_argv() -> None:
    loader = _source("deploy/shared/load-env.sh")
    assert "eval" not in loader
    assert "xargs" not in loader
    assert "export $(" not in loader
    for cloud in ("aws", "azure", "gcp"):
        script = _source(f"deploy/{cloud}/deploy.sh")
        assert "load_env_file" in script
        assert script.index("load_env_file") < script.index("# Configuration")
        assert "xargs" not in script
        assert "export $(" not in script


def test_aws_deploy_uses_precreated_secret_reference_not_provider_key_argv() -> None:
    script = _source("deploy/aws/deploy.sh")
    template = _source("deploy/aws/template.yaml")
    assert "ProviderSecretArn" in script
    assert 'ProviderSecretArn="$DEEPR_AWS_PROVIDER_SECRET_ARN"' in script
    assert "OpenAIApiKey=" not in script
    assert "GoogleApiKey=" not in script
    assert "XaiApiKey=" not in script
    assert "ProviderSecretArn:" in template
    assert "OpenAIApiKey:" not in template
    assert "SecretString: !Sub" not in template


def test_azure_deploy_passes_secret_values_through_protected_parameter_file() -> None:
    script = _source("deploy/azure/deploy.sh")
    assert "umask 077" in script
    assert "trap 'rm -f \"$PARAMETERS_FILE\"' EXIT" in script
    assert '--parameters "@$PARAMETERS_FILE"' in script
    assert 'openaiApiKey="$OPENAI_API_KEY"' not in script
    assert 'googleApiKey="${GOOGLE_API_KEY:-}"' not in script
    assert 'xaiApiKey="${XAI_API_KEY:-}"' not in script


def test_gcp_deploy_uses_precreated_secret_reference_and_ephemeral_tfvars() -> None:
    script = _source("deploy/gcp/deploy.sh")
    terraform = _source("deploy/gcp/main.tf")
    assert "umask 077" in script
    assert "trap 'rm -f \"$TFVARS_FILE\"' EXIT" in script
    assert '-var-file="$TFVARS_FILE"' in script
    assert "terraform.tfvars" not in script
    assert "DEEPR_GCP_OPENAI_SECRET_ID" in script
    assert '"openai_secret_id"' in script
    assert "OPENAI_API_KEY" not in script
    assert 'variable "openai_secret_id"' in terraform
    assert 'variable "openai_api_key"' not in terraform
    assert "var.openai_secret_id" in terraform
    assert "secret_data = var." not in terraform


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
