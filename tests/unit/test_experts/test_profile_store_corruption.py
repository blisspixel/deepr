"""Regression test: ``ExpertStore.list_all`` surfaces corruption rather
than silently dropping experts from the result.

Previously a corrupted profile.json was logged at WARNING and skipped,
so operators saw their expert "deleted" with no indication of why.
After the fix the log is ERROR level and the corruption list is
attached as an attribute on the returned list.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from deepr.experts.profile_store import ExpertStore


def _write_profile(base: Path, name: str, body: str) -> None:
    expert_dir = base / name
    expert_dir.mkdir(parents=True, exist_ok=True)
    (expert_dir / "profile.json").write_text(body, encoding="utf-8")


def _valid_profile_dict(name: str) -> dict:
    """Build a minimal but complete profile dict that ExpertProfile.from_dict accepts."""
    return {
        "name": name,
        "vector_store_id": "",
        "description": "test expert",
        "domain": "test",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
    }


class TestListAllCorruption:
    def test_corrupted_profile_logged_at_error(self, tmp_path, caplog):
        # Write one good and one corrupted profile.
        _write_profile(tmp_path, "good-expert", json.dumps(_valid_profile_dict("good-expert")))
        _write_profile(tmp_path, "broken-expert", "{not valid json")

        store = ExpertStore(str(tmp_path))
        with caplog.at_level("ERROR", logger="deepr.experts.profile_store"):
            profiles = store.list_all()

        # The good expert is returned.
        names = [p.name for p in profiles]
        assert "good-expert" in names
        # The broken one is NOT silently dropped — it surfaces in errors.
        assert "broken-expert" not in names
        # And is logged at ERROR (not WARNING) with the file path.
        assert any("broken-expert" in record.message for record in caplog.records)
        assert any(record.levelname == "ERROR" for record in caplog.records)

    def test_errors_attribute_on_result(self, tmp_path):
        _write_profile(tmp_path, "broken", "garbage")

        store = ExpertStore(str(tmp_path))
        profiles = store.list_all()

        # The corruption is reachable via the .errors attribute so admin
        # endpoints can surface it.
        errors = getattr(profiles, "errors", None)
        assert errors is not None
        assert len(errors) == 1
        path, reason = errors[0]
        assert "broken" in str(path)
        assert reason  # non-empty error description
