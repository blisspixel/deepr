"""Tests for the $0 exported-view validators."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.export_validation import (
    EXPORT_VALIDATION_SCHEMA_VERSION,
    validate_export,
)
from deepr.experts.handoff import HANDOFF_KIND, HANDOFF_SCHEMA_VERSION
from deepr.experts.okf import OKF_SCHEMA_VERSION


def _valid_handoff_payload() -> dict:
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "kind": HANDOFF_KIND,
        "generated_at": "2026-07-02T12:00:00+00:00",
        "contract": {
            "read_only": True,
            "canonical_state": ["expert profile", "belief store"],
            "derived_views": ["OKF bundles", "SKILL.md exports"],
        },
        "expert": {"name": "AI Strategy Expert", "domain": "ai"},
        "summary": {"claim_count": 3, "grounding_assurance": {"cross_vendor": 1}},
    }


def _checks_by_name(report: dict) -> dict[str, dict]:
    return {check["check"]: check for check in report["checks"]}


class TestHandoffValidation:
    def test_valid_handoff_passes_all_checks(self, tmp_path):
        path = tmp_path / "handoff.json"
        path.write_text(json.dumps(_valid_handoff_payload()), encoding="utf-8")

        report = validate_export(path)

        assert report["schema_version"] == EXPORT_VALIDATION_SCHEMA_VERSION
        assert report["artifact_class"] == "handoff_payload"
        assert report["status"] == "valid"
        assert report["failed_count"] == 0
        assert report["contract"]["semantic_judgment"] is False

    def test_handoff_missing_trust_metadata_fails_named_checks(self, tmp_path):
        payload = _valid_handoff_payload()
        payload["schema_version"] = "wrong-version"
        del payload["summary"]["grounding_assurance"]
        payload["contract"].pop("canonical_state")
        path = tmp_path / "handoff.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = validate_export(path)

        checks = _checks_by_name(report)
        assert report["status"] == "invalid"
        assert checks["schema_version"]["status"] == "fail"
        assert checks["grounding_assurance"]["status"] == "fail"
        assert checks["generated_view_class"]["status"] == "fail"
        assert checks["expert_provenance"]["status"] == "pass"

    def test_generated_view_class_detail_matches_failure_when_derived_views_missing(self, tmp_path):
        payload = _valid_handoff_payload()
        payload["contract"].pop("derived_views")
        path = tmp_path / "handoff.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = validate_export(path)

        check = _checks_by_name(report)["generated_view_class"]
        assert check["status"] == "fail"
        assert "does not declare" in check["detail"]

    def test_unparseable_json_fails_closed(self, tmp_path):
        path = tmp_path / "handoff.json"
        path.write_text("not json", encoding="utf-8")

        report = validate_export(path)

        assert report["status"] == "invalid"
        assert report["checks"][0]["check"] == "parseable_json"


class TestOkfValidation:
    def test_bundle_with_known_frontmatter_passes(self, tmp_path):
        bundle = tmp_path / "okf"
        bundle.mkdir()
        for name in ("index.md", "log.md"):
            (bundle / name).write_text(
                f"---\nschema_version: {OKF_SCHEMA_VERSION}\n---\n\n# {name}\n",
                encoding="utf-8",
            )

        report = validate_export(bundle)

        assert report["artifact_class"] == "okf_bundle"
        assert report["status"] == "valid"

    def test_bundle_with_unknown_schema_version_fails(self, tmp_path):
        bundle = tmp_path / "okf"
        bundle.mkdir()
        (bundle / "index.md").write_text("---\nschema_version: something-else\n---\n\n# index\n", encoding="utf-8")
        (bundle / "log.md").write_text(f"---\nschema_version: {OKF_SCHEMA_VERSION}\n---\n\n# log\n", encoding="utf-8")

        report = validate_export(bundle)

        checks = _checks_by_name(report)
        assert report["status"] == "invalid"
        assert checks["frontmatter_schema_versions"]["status"] == "fail"
        assert "index.md" in checks["frontmatter_schema_versions"]["detail"]


class TestSkillValidation:
    def test_generated_skill_export_passes(self, tmp_path):
        from deepr.skills.expert_skill import build_expert_skill

        path = tmp_path / "SKILL.md"
        path.write_text(
            build_expert_skill("AI Strategy Expert", "ai strategy", "Tracks AI strategy.").render(),
            encoding="utf-8",
        )

        report = validate_export(path)

        assert report["artifact_class"] == "skill_export"
        assert report["status"] == "valid", report["checks"]

    def test_skill_without_mcp_reference_fails_presence_check(self, tmp_path):
        path = tmp_path / "SKILL.md"
        path.write_text(
            "---\nname: x\ndescription: y\nversion: 1\nmcp_server: deepr\n---\n\nJust prose knowledge.\n",
            encoding="utf-8",
        )

        report = validate_export(path)

        checks = _checks_by_name(report)
        # Body check only; the frontmatter mcp_server value is a different check.
        assert checks["mcp_reference_present"]["status"] == "fail"
        assert report["status"] == "invalid"


class TestClassificationAndCli:
    def test_unknown_artifacts_and_missing_paths_are_invalid(self, tmp_path):
        report_missing = validate_export(tmp_path / "absent.json")
        stray = tmp_path / "notes.txt"
        stray.write_text("hello", encoding="utf-8")
        report_stray = validate_export(stray)

        assert report_missing["status"] == "invalid"
        assert report_stray["artifact_class"] == "unknown"
        assert report_stray["status"] == "invalid"

    def test_cli_exits_nonzero_on_invalid_and_zero_on_valid(self, tmp_path):
        good = tmp_path / "handoff.json"
        good.write_text(json.dumps(_valid_handoff_payload()), encoding="utf-8")
        bad = tmp_path / "broken.json"
        bad.write_text("{}", encoding="utf-8")

        ok = CliRunner().invoke(cli, ["expert", "validate-export", str(good), "--json"])
        fail = CliRunner().invoke(cli, ["expert", "validate-export", str(bad), "--json"])

        assert ok.exit_code == 0, ok.output
        assert json.loads(ok.output)["status"] == "valid"
        assert fail.exit_code == 1
        assert json.loads(fail.output)["status"] == "invalid"
