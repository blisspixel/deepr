"""Regression guard for the benchmark_models.py path resolution.

Both `deepr eval` and the auto-mode background eval invoke
`scripts/benchmark_models.py` by walking `Path(__file__).parents[N]`. The depth
count is easy to get wrong (it was: eval used parents[3] and auto_mode used
parents[1].parent, both resolving to a nonexistent ``src/scripts/`` and failing
the subprocess with rc=2). These tests pin the resolved path to the real file.
"""

from __future__ import annotations

from pathlib import Path

import deepr.routing.auto_mode as auto_mode
from deepr.cli.commands.eval import SCRIPT_PATH


def test_eval_script_path_points_at_real_benchmark_script():
    assert SCRIPT_PATH.name == "benchmark_models.py"
    assert SCRIPT_PATH.parent.name == "scripts"
    assert SCRIPT_PATH.exists(), f"eval SCRIPT_PATH does not exist: {SCRIPT_PATH}"


def test_auto_mode_resolves_same_benchmark_script():
    # Mirror the resolution inside auto_mode._run_eval (parents[3] = repo root).
    resolved = Path(auto_mode.__file__).resolve().parents[3] / "scripts" / "benchmark_models.py"
    assert resolved.exists(), f"auto_mode benchmark path does not exist: {resolved}"
    assert resolved == SCRIPT_PATH
