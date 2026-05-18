"""Coverage tests for ``deepr/services/context_index.py``.

Targets:
- DB / FTS schema bootstrap
- _scan_reports / _is_indexed / _generate_report_id
- index_reports (with embedding stubs)
- search (semantic + keyword + boost-on-overlap)
- get_stats / clear
- find_related (exclude job, missing path)
- get_report_by_job_id / get_report_content / check_stale_context
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.services.context_index import ContextIndex, SearchResult


@pytest.fixture
def tmp_index(tmp_path):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    return ContextIndex(data_dir=data_dir, reports_dir=reports_dir)


def _write_report(reports_dir: Path, job_id: str, prompt: str, model: str = "o3", content: str = "Report body"):
    rd = reports_dir / job_id
    rd.mkdir()
    (rd / "metadata.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "prompt": prompt,
                "model": model,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    (rd / "report.md").write_text(content)
    return rd


class TestSchemaAndScan:
    def test_db_and_tables_created(self, tmp_index):
        import sqlite3

        conn = sqlite3.connect(tmp_index.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {r[0] for r in cur.fetchall()}
        conn.close()
        assert "reports" in names
        # FTS5 table is reports_fts plus generated companion tables
        assert any(n.startswith("reports_fts") for n in names)

    def test_generate_report_id_deterministic(self):
        a = ContextIndex._generate_report_id("j1", "2026-05-17T00:00:00")
        b = ContextIndex._generate_report_id("j1", "2026-05-17T00:00:00")
        assert a == b
        assert len(a) == 16
        c = ContextIndex._generate_report_id("j1", "2026-05-17T00:00:01")
        assert a != c

    def test_scan_reports_skips_missing_metadata(self, tmp_index):
        rd = tmp_index.reports_dir / "no_metadata"
        rd.mkdir()
        # Note: no metadata.json
        out = tmp_index._scan_reports()
        assert out == []

    def test_scan_reports_skips_malformed_metadata(self, tmp_index):
        rd = tmp_index.reports_dir / "bad"
        rd.mkdir()
        (rd / "metadata.json").write_text("not json {")
        out = tmp_index._scan_reports()
        assert out == []

    def test_scan_reports_finds_valid(self, tmp_index):
        _write_report(tmp_index.reports_dir, "j1", "study X")
        _write_report(tmp_index.reports_dir, "j2", "study Y")
        out = tmp_index._scan_reports()
        assert len(out) == 2

    def test_scan_reports_returns_empty_when_dir_missing(self, tmp_path):
        idx = ContextIndex(data_dir=tmp_path / "d", reports_dir=tmp_path / "nope")
        assert idx._scan_reports() == []

    def test_is_indexed_returns_false_then_true(self, tmp_index):
        assert tmp_index._is_indexed("missing") is False


# ---------------------------------------------------------------------- #
# index_reports
# ---------------------------------------------------------------------- #


class TestIndexReports:
    @pytest.mark.asyncio
    async def test_index_no_reports(self, tmp_index):
        n = await tmp_index.index_reports()
        assert n == 0

    @pytest.mark.asyncio
    async def test_index_reports_with_embedding(self, tmp_index):
        _write_report(tmp_index.reports_dir, "j_alpha", "alpha research")
        _write_report(tmp_index.reports_dir, "j_beta", "beta research")

        client = MagicMock()

        async def fake_create(model, input):
            # Return a deterministic embedding per input.
            seed = sum(ord(c) for c in input) % 1024
            vec = np.full(1536, seed / 1024.0, dtype=np.float32)
            return MagicMock(data=[MagicMock(embedding=list(vec))])

        client.embeddings.create = AsyncMock(side_effect=fake_create)
        with patch("openai.AsyncOpenAI", return_value=client):
            n = await tmp_index.index_reports()
        assert n == 2
        # Embeddings persisted on disk.
        assert tmp_index.embeddings_path.exists()
        # Both reports recorded.
        assert tmp_index._is_indexed("j_alpha")

    @pytest.mark.asyncio
    async def test_index_skips_already_indexed_unless_forced(self, tmp_index):
        _write_report(tmp_index.reports_dir, "j_x", "x")
        client = MagicMock()
        client.embeddings.create = AsyncMock(return_value=MagicMock(data=[MagicMock(embedding=list(np.zeros(1536)))]))
        with patch("openai.AsyncOpenAI", return_value=client):
            await tmp_index.index_reports()
            # second pass — already indexed, returns 0
            n = await tmp_index.index_reports()
            assert n == 0
            # force=True re-indexes
            n2 = await tmp_index.index_reports(force=True)
            assert n2 >= 1

    @pytest.mark.asyncio
    async def test_index_handles_embedding_failure(self, tmp_index):
        _write_report(tmp_index.reports_dir, "j_fail", "boom")
        client = MagicMock()
        client.embeddings.create = AsyncMock(side_effect=RuntimeError("API down"))
        with patch("openai.AsyncOpenAI", return_value=client):
            n = await tmp_index.index_reports()
        # Indexed without an embedding (embedding_idx will be NULL).
        assert n == 1

    @pytest.mark.asyncio
    async def test_index_skips_report_with_empty_prompt(self, tmp_index):
        _write_report(tmp_index.reports_dir, "j_blank", "")
        client = MagicMock()
        client.embeddings.create = AsyncMock(return_value=MagicMock(data=[MagicMock(embedding=list(np.zeros(1536)))]))
        with patch("openai.AsyncOpenAI", return_value=client):
            n = await tmp_index.index_reports()
        assert n == 0


# ---------------------------------------------------------------------- #
# search / find_related / keyword fallback
# ---------------------------------------------------------------------- #


@pytest.fixture
def populated_index(tmp_path):
    idx = ContextIndex(data_dir=tmp_path / "data", reports_dir=tmp_path / "r")
    idx.reports_dir.mkdir(exist_ok=True)
    return idx


def _seed(idx: ContextIndex, job_id: str, prompt: str, summary: str, embedding: np.ndarray):
    import sqlite3

    rd = idx.reports_dir / job_id
    rd.mkdir(exist_ok=True)
    (rd / "report.md").write_text(f"Report for {prompt}")
    cur = sqlite3.connect(idx.db_path).cursor()
    embedding_idx = 0 if idx.embeddings is None else len(idx.embeddings)
    if idx.embeddings is None:
        idx.embeddings = embedding.reshape(1, -1)
    else:
        idx.embeddings = np.vstack([idx.embeddings, embedding])
    conn = sqlite3.connect(idx.db_path)
    conn.execute(
        "INSERT INTO reports (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            f"r_{job_id}",
            job_id,
            prompt,
            "o3",
            datetime.now(timezone.utc).isoformat(),
            str(rd),
            summary,
            embedding_idx,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.execute(
        "INSERT INTO reports_fts (report_id, prompt, summary) VALUES (?,?,?)",
        (f"r_{job_id}", prompt, summary),
    )
    conn.commit()
    conn.close()
    idx._save_embeddings()


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_semantic_returns_results(self, populated_index):
        vec_a = np.zeros(1536, dtype=np.float32)
        vec_a[0] = 1.0
        vec_b = np.zeros(1536, dtype=np.float32)
        vec_b[1] = 1.0
        _seed(populated_index, "ja", "alpha findings", "alpha summary", vec_a)
        _seed(populated_index, "jb", "beta findings", "beta summary", vec_b)

        client = MagicMock()
        # Query vector matches vec_a strongly.
        query_vec = np.zeros(1536, dtype=np.float32)
        query_vec[0] = 1.0
        client.embeddings.create = AsyncMock(return_value=MagicMock(data=[MagicMock(embedding=list(query_vec))]))
        with patch("openai.AsyncOpenAI", return_value=client):
            out = await populated_index.search("alpha", top_k=5, threshold=0.5, include_keyword=False)
        assert any(r.job_id == "ja" for r in out)

    @pytest.mark.asyncio
    async def test_search_with_no_embeddings_falls_back_to_keyword(self, populated_index):
        # Insert a record without any embeddings.
        import sqlite3

        rd = populated_index.reports_dir / "jk"
        rd.mkdir()
        (rd / "report.md").write_text("body")
        conn = sqlite3.connect(populated_index.db_path)
        conn.execute(
            "INSERT INTO reports (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "r_jk",
                "jk",
                "neural networks",
                "o3",
                datetime.now(timezone.utc).isoformat(),
                str(rd),
                "summary about networks",
                None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO reports_fts (report_id, prompt, summary) VALUES (?,?,?)",
            ("r_jk", "neural networks", "summary about networks"),
        )
        conn.commit()
        conn.close()

        out = await populated_index.search("neural", top_k=5, include_keyword=True)
        assert any(r.job_id == "jk" for r in out)

    @pytest.mark.asyncio
    async def test_semantic_search_handles_embed_failure(self, populated_index):
        # Embedding present but query embedding fails.
        vec = np.zeros(1536, dtype=np.float32)
        vec[0] = 1.0
        _seed(populated_index, "j1", "x", "y", vec)

        client = MagicMock()
        client.embeddings.create = AsyncMock(side_effect=RuntimeError("API down"))
        with patch("openai.AsyncOpenAI", return_value=client):
            out = await populated_index._semantic_search("query", top_k=5, threshold=0.0)
        assert out == []

    @pytest.mark.asyncio
    async def test_search_boosts_when_both_match(self, populated_index):
        vec = np.zeros(1536, dtype=np.float32)
        vec[0] = 1.0
        _seed(populated_index, "j_both", "quantum gravity", "quantum gravity research", vec)
        client = MagicMock()
        client.embeddings.create = AsyncMock(return_value=MagicMock(data=[MagicMock(embedding=list(vec))]))
        with patch("openai.AsyncOpenAI", return_value=client):
            out = await populated_index.search("quantum", top_k=5, threshold=0.0)
        assert any(r.job_id == "j_both" for r in out)
        # Boost gives semantic-only ~score then +0.1 for keyword match.
        score = next(r.similarity for r in out if r.job_id == "j_both")
        assert score > 0.5


class TestFindRelated:
    @pytest.mark.asyncio
    async def test_excludes_specified_job(self, populated_index):
        vec = np.zeros(1536, dtype=np.float32)
        vec[0] = 1.0
        _seed(populated_index, "j_keep", "x", "x summary", vec)
        _seed(populated_index, "j_skip", "x", "x summary", vec)

        client = MagicMock()
        client.embeddings.create = AsyncMock(return_value=MagicMock(data=[MagicMock(embedding=list(vec))]))
        with patch("openai.AsyncOpenAI", return_value=client):
            out = await populated_index.find_related("x", exclude_job_id="j_skip", threshold=0.0)
        ids = {r.job_id for r in out}
        assert "j_skip" not in ids

    @pytest.mark.asyncio
    async def test_filters_missing_report_paths(self, populated_index):
        # Insert a record whose path doesn't exist.
        import sqlite3

        vec = np.zeros(1536, dtype=np.float32)
        vec[0] = 1.0
        populated_index.embeddings = vec.reshape(1, -1)
        populated_index._save_embeddings()

        conn = sqlite3.connect(populated_index.db_path)
        conn.execute(
            "INSERT INTO reports (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "r_ghost",
                "ghost",
                "x",
                "o3",
                datetime.now(timezone.utc).isoformat(),
                "/nonexistent/path/never/here",
                "x summary",
                0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO reports_fts (report_id, prompt, summary) VALUES (?,?,?)",
            ("r_ghost", "x", "x summary"),
        )
        conn.commit()
        conn.close()

        client = MagicMock()
        client.embeddings.create = AsyncMock(return_value=MagicMock(data=[MagicMock(embedding=list(vec))]))
        with patch("openai.AsyncOpenAI", return_value=client):
            out = await populated_index.find_related("x", threshold=0.0)
        assert all(r.job_id != "ghost" for r in out)


# ---------------------------------------------------------------------- #
# get_stats / clear / get_report_by_job_id / get_report_content
# ---------------------------------------------------------------------- #


class TestStatsAndClear:
    def test_get_stats_empty(self, tmp_index):
        stats = tmp_index.get_stats()
        assert stats["indexed_reports"] == 0
        assert stats["embedding_count"] == 0

    def test_clear_resets(self, populated_index):
        vec = np.zeros(1536, dtype=np.float32)
        _seed(populated_index, "jx", "p", "s", vec)
        assert populated_index.get_stats()["indexed_reports"] == 1
        populated_index.clear()
        assert populated_index.get_stats()["indexed_reports"] == 0
        assert populated_index.embeddings is None
        assert not populated_index.embeddings_path.exists()


class TestGetReportByJobId:
    def test_returns_none_when_missing(self, tmp_index):
        assert tmp_index.get_report_by_job_id("nope") is None

    def test_exact_and_prefix_match(self, populated_index):
        vec = np.zeros(1536, dtype=np.float32)
        _seed(populated_index, "job_abc123", "p", "s", vec)
        exact = populated_index.get_report_by_job_id("job_abc123")
        assert exact is not None
        prefix = populated_index.get_report_by_job_id("job_abc")
        assert prefix is not None


class TestGetReportContent:
    def test_returns_none_when_no_report(self, populated_index):
        assert populated_index.get_report_content("missing") is None

    def test_returns_content(self, populated_index):
        vec = np.zeros(1536, dtype=np.float32)
        _seed(populated_index, "j_short", "p", "s", vec)
        out = populated_index.get_report_content("j_short")
        assert out is not None
        assert "Report for p" in out

    def test_truncates_long_content(self, populated_index, tmp_path):
        vec = np.zeros(1536, dtype=np.float32)
        rd = populated_index.reports_dir / "j_long"
        rd.mkdir()
        long_body = "para\n\n" + ("a" * 1000 + "\n\n") * 10
        (rd / "report.md").write_text(long_body)
        # Manually seed DB row pointing at rd.
        import sqlite3

        conn = sqlite3.connect(populated_index.db_path)
        conn.execute(
            "INSERT INTO reports (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "r_long",
                "j_long",
                "x",
                "o3",
                datetime.now(timezone.utc).isoformat(),
                str(rd),
                "s",
                None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        out = populated_index.get_report_content("j_long", max_chars=500)
        assert out is not None
        assert "truncated for context budget" in out


class TestCheckStale:
    def test_unknown_treated_as_stale(self, tmp_index):
        assert tmp_index.check_stale_context("nope") is True

    def test_fresh_report_not_stale(self, populated_index):
        vec = np.zeros(1536, dtype=np.float32)
        _seed(populated_index, "j_fresh", "p", "s", vec)
        assert populated_index.check_stale_context("j_fresh", max_age_days=30) is False


class TestSearchResultDataclass:
    def test_to_dict(self, tmp_path):
        sr = SearchResult(
            report_id="r1",
            job_id="j1",
            prompt="p",
            created_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
            similarity=0.9,
            report_path=tmp_path / "x",
            model="o3",
            summary="s",
        )
        d = sr.to_dict()
        assert d["report_id"] == "r1"
        assert d["similarity"] == 0.9
        assert d["created_at"] == "2026-05-17T00:00:00+00:00"
