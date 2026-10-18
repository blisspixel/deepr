"""Failed first-build evidence is inspectable without promoting candidates."""

import json

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.expert_health import assess_expert
from deepr.experts.formation import read_formation_state
from deepr.experts.profile import ExpertProfile, ExpertStore


def test_failed_first_study_status_health_next_and_retain_agree(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "experts"))
    store = ExpertStore()
    profile = ExpertProfile(name="Bread", vector_store_id="local", provider="local", model="too-small")
    store.save(profile)
    directory = store.find_existing_dir(profile.name)
    operation = "a" * 32
    candidate = directory / "formation/runs" / operation
    candidate.mkdir(parents=True)
    state = {
        "schema_version": "deepr-formation-v1",
        "status": "incomplete",
        "model": "too-small",
        "operation_id": operation,
    }
    (directory / "formation/current.json").write_text(json.dumps(state))
    (candidate / "study.json").write_text(
        json.dumps(
            {
                "model": "actually-ran",
                "started_at": "2026-10-17T00:00:00Z",
                "totals": {"findings": 12, "grounded_findings": 0},
            }
        )
    )
    note = tmp_path / "source.md"
    note.write_text("A retained source describing bread fermentation.")
    retained = CliRunner().invoke(cli, ["expert", "retain", "Bread", str(note)])
    assert retained.exit_code == 0, retained.output
    assert "expert build Bread --no-discovery" in retained.output
    before = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    status = CliRunner().invoke(cli, ["expert", "status", "Bread", "--json"])
    assert status.exit_code == 0, status.output
    payload = json.loads(status.output)
    study = next(item for item in payload["stages"] if item["stage"] == "study")
    assert study["status"] == "failed"
    assert "0 of 12 findings anchored" in study["success_means"]
    assert "actually-ran" in study["success_means"]
    assert payload["next"] == "build"
    health = assess_expert("Bread", directory)
    assert health.is_studied and health.findings == 12 and health.grounded_findings == 0
    assert "0 of 12 findings anchored" in health.next_action
    assert "expert build Bread --no-discovery" in health.next_action
    next_result = CliRunner().invoke(cli, ["expert", "next", "Bread", "--json"])
    assert next_result.exit_code == 0, next_result.output
    actions = json.loads(next_result.output)["next_actions"]
    assert len(actions) == 1
    assert actions[0] == payload["next_action"]
    assert all(path.read_bytes() == content for path, content in before.items())
    assert not (directory / "noticed/current.json").exists()


def test_candidate_operation_cannot_escape_expert_root(tmp_path):
    (tmp_path / "formation").mkdir()
    (tmp_path / "formation/current.json").write_text(
        json.dumps(
            {
                "schema_version": "deepr-formation-v1",
                "operation_id": "../../outside",
                "status": "incomplete",
            }
        )
    )
    state = read_formation_state("Bread", directory=tmp_path)
    assert "study_attempt" not in state


def test_completed_formation_without_published_artifacts_cannot_select_model(tmp_path, monkeypatch):
    from deepr.experts.formation import _snapshot, successful_formation_model

    monkeypatch.setattr("deepr.experts.formation.canonical_expert_dir", lambda _: tmp_path)
    (tmp_path / "formation").mkdir()
    (tmp_path / "formation/current.json").write_text(
        json.dumps(
            {
                "schema_version": "deepr-formation-v1",
                "status": "research_complete",
                "capacity_source": "local:small",
                "model": "small",
                "final_artifacts": _snapshot(tmp_path),
            }
        )
    )
    assert successful_formation_model("Bread") is None
