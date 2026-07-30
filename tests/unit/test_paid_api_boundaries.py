"""Regression tests for the repository-wide paid API boundary."""

from __future__ import annotations

import ast
import runpy
from pathlib import Path

import pytest
import yaml

from scripts import check_paid_api_boundaries

_RETIRED_PAID_SCRIPTS = (
    "research_mcp_best_practices.py",
    "upload_mcp_docs_to_expert.py",
)

_DURABLY_METERED_LEGACY_CALLERS = (
    "citation_validator.py",
    "curriculum.py",
    "gap_discovery.py",
    "map_reduce.py",
    "multi_pass.py",
    "reflection.py",
    "synthesis.py",
    "task_planner.py",
)


@pytest.mark.parametrize("script_name", _RETIRED_PAID_SCRIPTS)
def test_retired_paid_script_fails_closed(script_name: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Legacy one-off scripts exit before importing or constructing a paid client."""
    script_path = Path(__file__).parents[2] / "scripts" / script_name
    tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=script_name)
    provider_roots = {"openai", "anthropic", "google", "xai_sdk", "azure"}
    imported_roots = {
        alias.name.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(name=node.module or "")])
    }
    assert imported_roots.isdisjoint(provider_roots)

    namespace = runpy.run_path(str(script_path), run_name="retired_paid_script_test")
    assert namespace["main"]() == 2
    assert "Disabled:" in capsys.readouterr().err


def test_paid_boundary_ratchet_rejects_new_constructor(tmp_path: Path, monkeypatch, capsys) -> None:
    """A new paid SDK construction site fails without an audited baseline entry."""
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "from openai import OpenAI\nclient = OpenAI()\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})

    assert check_paid_api_boundaries.main() == 1
    output = capsys.readouterr().out
    assert "src/deepr/unsafe.py" in output
    assert "audited baseline 0" in output


def test_paid_boundary_ratchet_rejects_new_raw_endpoint(tmp_path: Path, monkeypatch, capsys) -> None:
    """A new raw provider endpoint fails without an audited baseline entry."""
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        'url = "https://api.openai.com/v1/responses"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})

    assert check_paid_api_boundaries.main() == 1
    output = capsys.readouterr().out
    assert "src/deepr/unsafe.py" in output
    assert "paid-endpoint references" in output


def test_paid_boundary_rejects_sdk_client_without_explicit_endpoint(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "from openai import AsyncOpenAI\nclient = AsyncOpenAI(api_key='test')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {"src/deepr/unsafe.py": 1})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_REQUIRED_SAFETY_FRAGMENTS", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_CLOUD_DEPLOY_SCRIPTS", ())

    assert check_paid_api_boundaries.main() == 1
    assert "does not pin an explicit reviewed base_url" in capsys.readouterr().out


def test_paid_boundary_rejects_generic_metered_client_without_endpoint_guard(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "from deepr.services.metered_call import execute_reserved_sync_call\n"
        "def run(client):\n"
        "    return execute_reserved_sync_call(operation_prefix='x', provider='openai', model='gpt-5', "
        "source='test', max_cost_per_job=1.0, request_envelope={'model': 'gpt-5'}, call=lambda: None)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_REQUIRED_SAFETY_FRAGMENTS", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_CLOUD_DEPLOY_SCRIPTS", ())

    assert check_paid_api_boundaries.main() == 1
    assert "lacks an official live-client endpoint guard" in capsys.readouterr().out


def test_paid_boundary_rejects_metered_wrapper_without_explicit_ceiling(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "from deepr.services.metered_call import execute_reserved_sync_call\n"
        "execute_reserved_sync_call(operation_prefix='x', provider='openai', model='gpt-5', "
        "source='test', call=lambda: None)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})

    assert check_paid_api_boundaries.main() == 1
    assert "metered call lacks explicit max_cost_per_job" in capsys.readouterr().out


def test_paid_boundary_rejects_metered_wrapper_without_request_envelope(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "from deepr.services.metered_call import execute_reserved_sync_call\n"
        "execute_reserved_sync_call(operation_prefix='x', provider='openai', model='gpt-5', "
        "source='test', max_cost_per_job=1.0, call=lambda: None)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})

    assert check_paid_api_boundaries.main() == 1
    assert "metered call lacks exact request_envelope" in capsys.readouterr().out


def test_paid_boundary_rejects_gemini_client_with_default_sdk_retries(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "from google import genai\nclient = genai.Client(api_key='test')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {"src/deepr/unsafe.py": 1})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})

    assert check_paid_api_boundaries.main() == 1
    assert "Gemini client does not pin SDK attempts=1" in capsys.readouterr().out


def test_paid_boundary_accepts_gemini_client_with_one_sdk_attempt(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "safe.py").write_text(
        "from google import genai\n"
        "from deepr.providers.dispatch_authority import default_paid_endpoint\n"
        "client = genai.Client(vertexai=False, api_key='test', http_options={"
        "'base_url': default_paid_endpoint('gemini'), "
        "'retry_options': {'attempts': 1}, "
        "'client_args': {'trust_env': False, 'follow_redirects': False}, "
        "'async_client_args': {'trust_env': False, 'follow_redirects': False}})\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {"src/deepr/safe.py": 1})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_REQUIRED_SAFETY_FRAGMENTS", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_CLOUD_DEPLOY_SCRIPTS", ())

    assert check_paid_api_boundaries.main() == 0
    assert "Gemini client does not pin" not in capsys.readouterr().out


def test_paid_boundary_rejects_gemini_client_with_proxy_aware_transport(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "from google import genai\n"
        "client = genai.Client(api_key='test', http_options={'retry_options': {'attempts': 1}})\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {"src/deepr/unsafe.py": 1})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})

    assert check_paid_api_boundaries.main() == 1
    assert "Gemini client does not disable proxy inheritance and redirects" in capsys.readouterr().out


def test_paid_boundary_rejects_unreviewed_httpx_client(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "unsafe.py").write_text(
        "import httpx\nclient = httpx.AsyncClient(timeout=10)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})

    assert check_paid_api_boundaries.main() == 1
    assert "httpx client must set trust_env=False and follow_redirects=False" in capsys.readouterr().out


def test_paid_boundary_accepts_hardened_httpx_clients(tmp_path: Path, monkeypatch, capsys) -> None:
    scan_root = tmp_path / "src" / "deepr"
    scan_root.mkdir(parents=True)
    (scan_root / "safe.py").write_text(
        "from httpx import AsyncClient, Client\n"
        "sync_client = Client(trust_env=False, follow_redirects=False)\n"
        "async_client = AsyncClient(trust_env=False, follow_redirects=False)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (scan_root,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_REQUIRED_SAFETY_FRAGMENTS", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_CLOUD_DEPLOY_SCRIPTS", ())

    assert check_paid_api_boundaries.main() == 0
    assert "httpx client must set" not in capsys.readouterr().out


def test_paid_boundary_rejects_removed_safety_quarantine(tmp_path: Path, monkeypatch, capsys) -> None:
    boundary = tmp_path / "src" / "deepr" / "boundary.py"
    boundary.parent.mkdir(parents=True)
    boundary.write_text("EXECUTION_ENABLED = True\n", encoding="utf-8")

    monkeypatch.setattr(check_paid_api_boundaries, "_ROOT", tmp_path)
    monkeypatch.setattr(check_paid_api_boundaries, "_SCAN_ROOTS", (boundary.parent,))
    monkeypatch.setattr(check_paid_api_boundaries, "_BASELINE", {})
    monkeypatch.setattr(check_paid_api_boundaries, "_ENDPOINT_BASELINE", {})
    monkeypatch.setattr(
        check_paid_api_boundaries,
        "_REQUIRED_SAFETY_FRAGMENTS",
        {"src/deepr/boundary.py": ("EXECUTION_ENABLED = False",)},
    )
    monkeypatch.setattr(check_paid_api_boundaries, "_CLOUD_DEPLOY_SCRIPTS", ())

    assert check_paid_api_boundaries.main() == 1
    assert "required safety boundary is missing" in capsys.readouterr().out


def test_current_paid_boundary_ratchet_passes() -> None:
    """The checked-in paid client inventory cannot exceed its audited baseline."""
    assert check_paid_api_boundaries.main() == 0


@pytest.mark.parametrize("workflow_name", ["ci.yml", "mutation.yml"])
def test_every_hosted_ci_job_has_a_finite_timeout(workflow_name: str) -> None:
    workflow_path = Path(__file__).parents[2] / ".github" / "workflows" / workflow_name
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert workflow["jobs"]
    for job_name, job in workflow["jobs"].items():
        timeout = job.get("timeout-minutes")
        assert isinstance(timeout, int), f"{workflow_name}:{job_name} has no finite timeout"
        assert 1 <= timeout <= 120


@pytest.mark.parametrize("workflow_name", ["ci.yml", "mutation.yml"])
def test_hosted_ci_cancels_superseded_runs(workflow_name: str) -> None:
    workflow_path = Path(__file__).parents[2] / ".github" / "workflows" / workflow_name
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert workflow["concurrency"]["group"]
    assert workflow["concurrency"]["cancel-in-progress"] is True


def test_sbom_artifact_has_short_explicit_retention() -> None:
    workflow_path = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    upload_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]

    assert upload_steps
    for step in upload_steps:
        assert 1 <= int(step["with"]["retention-days"]) <= 7


@pytest.mark.parametrize("module_name", _DURABLY_METERED_LEGACY_CALLERS)
def test_migrated_paid_caller_keeps_durable_bounded_accounting(module_name: str) -> None:
    """Migrated callers cannot regress to estimate-only or unbounded dispatch."""
    module_path = Path(__file__).parents[2] / "src" / "deepr" / "experts" / module_name
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=module_name)
    imported_symbols = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "deepr.experts.cost_admission"
        for alias in node.names
    }
    keyword_names = {
        keyword.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg is not None
    }
    metered_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute_reserved_async_call"
    ]

    assert not ({"admit_soft_cost_operation", "record_soft_cost"} & imported_symbols)
    assert "execute_reserved_async_call" in source
    assert "bounded_metered_completion_kwargs" in source
    assert "max_completion_tokens" in source
    assert "max_tokens" not in keyword_names
    assert metered_calls
    assert all(
        any(
            keyword.arg == "max_cost_per_job"
            and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
            for keyword in call.keywords
        )
        for call in metered_calls
    )
    assert all(
        any(
            keyword.arg == "request_envelope"
            and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
            for keyword in call.keywords
        )
        for call in metered_calls
    )
