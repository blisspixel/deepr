"""Tests for MCP artifact_ids helper utilities."""

from deepr.mcp.artifacts import ArtifactManifest, build_artifact_ids, inject_artifact_ids


class TestArtifactManifest:
    def test_to_dict_minimal(self):
        manifest = ArtifactManifest(trace_id="t1")
        d = manifest.to_dict()
        assert d == {"trace_id": "t1"}

    def test_to_dict_full(self):
        manifest = ArtifactManifest(
            trace_id="t1",
            job_id="j1",
            report_id="r1",
            expert_id="e1",
            session_id="s1",
            workflow_id="w1",
        )
        d = manifest.to_dict()
        assert d == {
            "trace_id": "t1",
            "job_id": "j1",
            "report_id": "r1",
            "expert_id": "e1",
            "session_id": "s1",
            "workflow_id": "w1",
        }

    def test_to_dict_excludes_empty(self):
        manifest = ArtifactManifest(trace_id="t1", job_id="j1")
        d = manifest.to_dict()
        assert "report_id" not in d
        assert "expert_id" not in d

    def test_default_trace_id(self):
        manifest = ArtifactManifest()
        assert len(manifest.trace_id) == 16


class TestBuildArtifactIds:
    def test_with_trace_id(self):
        ids = build_artifact_ids(trace_id="abc", job_id="j1")
        assert ids == {"trace_id": "abc", "job_id": "j1"}

    def test_auto_generates_trace_id(self):
        ids = build_artifact_ids(job_id="j1")
        assert "trace_id" in ids
        assert len(ids["trace_id"]) == 16

    def test_excludes_empty_values(self):
        ids = build_artifact_ids(trace_id="t1", job_id="", session_id="s1")
        assert "job_id" not in ids
        assert ids == {"trace_id": "t1", "session_id": "s1"}


class TestInjectArtifactIds:
    def test_adds_artifact_ids_to_response(self):
        response = {"status": "ok", "job_id": "j1"}
        result = inject_artifact_ids(response, trace_id="t1", job_id="j1")

        assert result is response  # mutates in place
        assert "artifact_ids" in result
        assert result["artifact_ids"]["trace_id"] == "t1"
        assert result["artifact_ids"]["job_id"] == "j1"

    def test_preserves_existing_keys(self):
        response = {"status": "ok", "data": [1, 2, 3]}
        inject_artifact_ids(response, trace_id="t1")
        assert response["status"] == "ok"
        assert response["data"] == [1, 2, 3]
        assert "artifact_ids" in response
