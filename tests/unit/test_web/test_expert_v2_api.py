"""The v2 expert layer, over HTTP.

Before these routes existed the web API served an expert as `document_count`,
`finding_count`, `gap_count` and `total_cost` - fields that describe any CRUD
application. Nothing that makes an expert an expert was reachable from a
browser: no standpoint, no positions, no evidence chain.

Two properties carry most of the weight here.

**Absent is 404, empty is 200.** An expert with no brief has no positions
*file*; returning an empty list instead would assert that the expert holds no
views, which is a claim about the expert rather than about the pipeline.

**A source is addressed by sha256 and nothing else.** `CorpusStore.read` builds
`sources/<sha[:2]>/<sha>.md` by interpolation, so an unvalidated sha walks out
of the corpus directory. The format check is the confinement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("flask")

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

from deepr.experts import expert_layout
from deepr.web.app import app


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def fleet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A one-expert fleet on disk, in the current layout."""
    monkeypatch.setattr(expert_layout._paths, "canonical_expert_dir", lambda name: tmp_path / name)
    directory = tmp_path / "flooding"
    (directory / "hold").mkdir(parents=True)
    (directory / "graph").mkdir(parents=True)
    (directory / "self.json").write_text(
        json.dumps(
            {
                "expert_name": "flooding",
                "chosen_name": "Marlowe",
                "standpoint": "I read this as a systems problem.",
                "glad_to_be_asked_about": ["what breaks first"],
                "shifts": [{"at": "2026-01-01T00:00:00+00:00", "was": "x", "now": "y", "because": "z"}],
            }
        ),
        encoding="utf-8",
    )
    (directory / "hold" / "current.json").write_text(
        json.dumps({"positions": [{"question": "Q", "would_change_my_mind": "a counterexample"}]}), encoding="utf-8"
    )
    (directory / "graph" / "evidence.json").write_text(json.dumps({"stats": {"is_formed": True}}), encoding="utf-8")
    return tmp_path


class TestTheSelfAccount:
    """The screen that lets a human pick which of fifty-seven experts to ask."""

    def test_it_serves_what_the_expert_calls_itself(self, client, fleet) -> None:
        payload = client.get("/api/experts/flooding/self").get_json()
        assert payload["self"]["chosen_name"] == "Marlowe"
        assert payload["self"]["standpoint"] == "I read this as a systems problem."
        assert payload["self"]["glad_to_be_asked_about"] == ["what breaks first"]

    def test_derived_flags_are_computed_not_trusted(self, client, fleet) -> None:
        """A stale file must not be able to disagree with the flags the UI branches on."""
        payload = client.get("/api/experts/flooding/self").get_json()
        assert payload["self"]["has_standpoint"] is True
        assert payload["self"]["has_changed_its_mind"] is True
        assert isinstance(payload["self"]["concerns"], list)

    def test_an_expert_with_no_self_account_is_404_not_empty(self, client, fleet) -> None:
        (fleet / "silent").mkdir()
        response = client.get("/api/experts/silent/self")
        assert response.status_code == 404
        assert "self-account" in response.get_json()["error"]

    def test_every_response_states_it_cost_nothing(self, client, fleet) -> None:
        assert client.get("/api/experts/flooding/hold").get_json()["cost_usd"] == 0.0


class TestAbsentIsNotEmpty:
    """Each artifact says it is missing rather than returning a hollow shape."""

    @pytest.mark.parametrize(
        "route",
        [
            "hold",
            "hold/history",
            "noticed",
            "became",
            "attend",
            "met/examination",
            "evidence",
            "corpus",
        ],
    )
    def test_a_missing_artifact_is_404(self, client, fleet, route: str) -> None:
        (fleet / "bare").mkdir()
        assert client.get(f"/api/experts/bare/{route}").status_code == 404

    def test_a_present_artifact_is_200(self, client, fleet) -> None:
        assert client.get("/api/experts/flooding/hold").status_code == 200
        assert client.get("/api/experts/flooding/evidence").status_code == 200

    def test_unparseable_json_reads_as_absent(self, client, fleet) -> None:
        """Half a document rendered as fact is worse than saying it is gone."""
        (fleet / "flooding" / "hold" / "current.json").write_text("{ not json", encoding="utf-8")
        assert client.get("/api/experts/flooding/hold").status_code == 404


class TestASourceIsAddressedByItsHash:
    """The endpoint that lets a claim reach the sentence it rests on."""

    @pytest.mark.parametrize(
        "bad",
        [
            "abc",
            "A" * 64,
            "0" * 63,
            "0" * 65,
            "../../../../etc/passwd",
            "..%2f..%2fsecret",
            "0123456789abcdef" * 3 + "0123456789abcde/",
        ],
    )
    def test_anything_that_is_not_a_sha256_is_refused(self, client, fleet, bad: str) -> None:
        response = client.get(f"/api/experts/flooding/source/{bad}")
        assert response.status_code in (400, 404), f"{bad!r} reached the filesystem"

    def test_a_well_formed_hash_that_is_not_retained_is_404(self, client, fleet) -> None:
        assert client.get(f"/api/experts/flooding/source/{'a' * 64}").status_code == 404

    def test_traversal_never_reads_a_file(self, client, fleet, tmp_path: Path) -> None:
        """The bug this guards: sha is interpolated straight into a path."""
        secret = tmp_path / "secret.md"
        secret.write_text("do not serve me", encoding="utf-8")
        response = client.get("/api/experts/flooding/source/..%2F..%2Fsecret")
        assert response.status_code in (400, 404)
        assert b"do not serve me" not in response.data
