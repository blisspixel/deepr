"""Regression tests for the repository-wide paid API boundary."""

from __future__ import annotations

import ast
import runpy
from pathlib import Path

import pytest

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


def test_current_paid_boundary_ratchet_passes() -> None:
    """The checked-in paid client inventory cannot exceed its audited baseline."""
    assert check_paid_api_boundaries.main() == 0


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
