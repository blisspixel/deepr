"""Deploy model allowlists stay on one current list and the shared sunset table."""

from __future__ import annotations

import ast
import importlib.util
from datetime import date
from pathlib import Path

from deepr.routing.deprecation import is_shutdown, model_submission_error

REPO_ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST_FILES = (
    "deploy/shared/deepr_api_common/validation.py",
    "deploy/aws/src/api/handler.py",
    "deploy/azure/functions/function_app.py",
    "deploy/gcp/functions/main.py",
)
CURRENT_MODELS = ["gpt-5.6-sol", "gpt-5.6-terra"]
REMOVED_MODELS = {
    "o3-deep-research",
    "o4-mini-deep-research",
    "grok-3-fast",
    "grok-3-mini-fast",
    "gemini-2.0-flash-thinking-exp",
    "gemini-2.5-pro-exp-03-25",
}


def _assigned_list(relative: str, name: str) -> list[str]:
    tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = ast.literal_eval(node.value)
                assert isinstance(value, list)
                return value
    raise AssertionError(f"{relative} has no {name} assignment")


def _submit_source(relative: str) -> str:
    source = (REPO_ROOT / relative).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "submit_job")
    segment = ast.get_source_segment(source, function)
    assert segment is not None
    return segment


def test_deploy_allowlists_share_one_current_list() -> None:
    lists = [_assigned_list(relative, "VALID_MODELS") for relative in ALLOWLIST_FILES]
    assert lists == [CURRENT_MODELS, CURRENT_MODELS, CURRENT_MODELS, CURRENT_MODELS]
    assert REMOVED_MODELS.isdisjoint(lists[0])


def test_deploy_allowlist_rejects_a_recorded_sunset_that_has_passed() -> None:
    """Fails when any copied allowlist entry is already past its recorded sunset."""
    for model in _assigned_list(ALLOWLIST_FILES[0], "VALID_MODELS"):
        assert not is_shutdown(model), model


def test_submission_error_uses_the_recorded_sunset_before_the_allowlist() -> None:
    shut_down = model_submission_error("o3-deep-research", CURRENT_MODELS, today=date(2026, 11, 3))
    assert shut_down is not None
    assert shut_down["error_code"] == "model_shut_down"
    grok = model_submission_error("grok-3-fast", CURRENT_MODELS, today=date(2026, 11, 3))
    assert grok is not None
    assert grok["error_code"] == "model_shut_down"
    unknown = model_submission_error("gemini-2.0-flash-thinking-exp", CURRENT_MODELS, today=date(2026, 11, 3))
    assert unknown == {"error": "Invalid model. Valid options: gpt-5.6-sol, gpt-5.6-terra"}
    assert model_submission_error("gpt-5.6-sol", CURRENT_MODELS, today=date(2026, 11, 3)) is None
    assert model_submission_error(None, CURRENT_MODELS) == {
        "error": "Invalid model. Valid options: gpt-5.6-sol, gpt-5.6-terra"
    }


def test_reference_handlers_refuse_shutdown_after_the_execution_gate() -> None:
    for relative, gate in (
        ("deploy/aws/src/api/handler.py", "if not AWS_METERED_RESEARCH_EXECUTION_ENABLED"),
        ("deploy/azure/functions/function_app.py", "if not AZURE_METERED_RESEARCH_EXECUTION_ENABLED"),
        ("deploy/gcp/functions/main.py", "if not GCP_METERED_RESEARCH_EXECUTION_ENABLED"),
    ):
        source = _submit_source(relative)
        assert source.index(gate) < source.index("model_submission_error")
        assert "model_shut_down" not in source


def test_shared_validator_reports_the_shutdown_message() -> None:
    path = REPO_ROOT / "deploy/shared/deepr_api_common/validation.py"
    spec = importlib.util.spec_from_file_location("test_deepr_api_common_validation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    valid, _model, error = module.validate_model("o3-deep-research")
    assert valid is False
    assert error == "Model o3-deep-research is shut down by its provider"
    valid, model, error = module.validate_model("gpt-5.6-terra")
    assert (valid, model, error) == (True, "gpt-5.6-terra", None)
