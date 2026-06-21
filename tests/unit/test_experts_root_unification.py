"""Experts-root unification (ADR 0004): one configurable root for all expert data.

Mirrors test_report_root_unification.py. The guard test is the safety net
against the split-store failure mode: if any module hardcodes data/experts
instead of deepr.config.experts_root(), expert data silently splits across two
roots when the user points DEEPR_DATA_DIR at a synced folder.
"""

from __future__ import annotations

import pathlib

import pytest

from deepr.config import experts_root

_DEEPR_PKG = pathlib.Path(__file__).resolve().parents[2] / "deepr"
# Functional hardcode patterns (not docstrings/comments, which mention the path).
_FORBIDDEN = ('Path("data/experts"', '"data/experts")', ': str = "data/experts"')


class TestNoHardcodedRoot:
    def test_no_module_hardcodes_the_experts_root(self):
        offenders = []
        for py in _DEEPR_PKG.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if any(pat in text for pat in _FORBIDDEN):
                offenders.append(str(py.relative_to(_DEEPR_PKG.parent)))
        assert not offenders, (
            "These modules hardcode the experts root; use deepr.config.experts_root() instead "
            f"(ADR 0004): {offenders}"
        )


class TestResolution:
    def test_default_data_dir_is_user_home_not_cwd(self):
        # Generic + CWD-independent: no username hard-coded, resolves from home.
        from deepr.config import default_data_dir

        assert default_data_dir() == pathlib.Path.home() / ".deepr"

    def test_default_is_stable_per_user_home(self, monkeypatch):
        # Unset -> a stable per-user home (~/.deepr), CWD-independent, so a
        # globally-installed CLI finds the same experts from any directory
        # (not the old ./data that only resolved inside a checkout).
        monkeypatch.delenv("DEEPR_EXPERTS_PATH", raising=False)
        monkeypatch.delenv("DEEPR_DATA_DIR", raising=False)
        assert experts_root() == pathlib.Path.home() / ".deepr" / "experts"

    def test_data_dir_moves_the_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEEPR_EXPERTS_PATH", raising=False)
        monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))
        assert experts_root() == tmp_path / "experts"

    def test_explicit_experts_path_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "ignored"))
        monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "custom"))
        assert experts_root() == tmp_path / "custom"

    def test_suite_is_isolated_from_real_experts_root(self):
        # Regression: the autouse _isolate_experts_root fixture (conftest) keeps
        # the suite out of the user's real data/experts/. Tests leaked MagicMock,
        # test_expert, and stray expert directories there before it existed. No
        # env override here - it relies on the fixture being active.
        root = experts_root()
        assert root != pathlib.Path("data") / "experts"
        assert root.resolve() != (pathlib.Path.cwd() / "data" / "experts").resolve()


class TestComponentsHonorRoot:
    def test_belief_store_writes_under_configured_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEEPR_EXPERTS_PATH", raising=False)
        monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))
        from deepr.experts.beliefs import BeliefStore

        store = BeliefStore("Portable Expert")
        # One expert = one canonical (slugified) directory under the configured
        # root; the display name lives in profile.json, not the path.
        assert store.storage_dir == tmp_path / "experts" / "portable_expert" / "beliefs"

    def test_expert_store_writes_under_configured_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEEPR_EXPERTS_PATH", raising=False)
        monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))
        from deepr.experts.profile_store import ExpertStore

        assert ExpertStore().base_path == tmp_path / "experts"

    def test_subscription_store_follows_expert_store(self, tmp_path, monkeypatch):
        # SubscriptionStore derives from ExpertStore.get_knowledge_dir, so it
        # must move with the configured root too (transitive coverage).
        monkeypatch.delenv("DEEPR_EXPERTS_PATH", raising=False)
        monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))
        from deepr.experts.sync import SubscriptionStore

        store = SubscriptionStore("Portable Expert")
        assert str(tmp_path) in str(store.path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
