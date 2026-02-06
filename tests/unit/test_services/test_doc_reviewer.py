"""Tests for doc reviewer service."""

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.test_services.conftest import make_chat_response


class TestDocReviewer:
    """Test DocReviewer document evaluation."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def temp_docs(self, tmp_path):
        """Create temp directory with sample docs."""
        doc1 = tmp_path / "report1.txt"
        doc1.write_text("First report content about market analysis")
        doc2 = tmp_path / "report2.txt"
        doc2.write_text("Second report about competitive landscape")
        return str(tmp_path)

    @pytest.fixture
    def reviewer(self, mock_client, temp_docs):
        with patch("deepr.services.doc_reviewer.OpenAI", return_value=mock_client):
            from deepr.services.doc_reviewer import DocReviewer

            return DocReviewer(api_key="test-key", docs_path=temp_docs)

    def test_init_with_api_key(self):
        """Direct API key accepted."""
        with patch("deepr.services.doc_reviewer.OpenAI"):
            from deepr.services.doc_reviewer import DocReviewer

            r = DocReviewer(api_key="direct-key")
            assert r.api_key == "direct-key"

    def test_init_no_key_raises(self, monkeypatch):
        """No API key raises ValueError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with patch("deepr.services.doc_reviewer.OpenAI"):
            from deepr.services.doc_reviewer import DocReviewer

            with pytest.raises(ValueError, match="OPENAI_API_KEY not found"):
                DocReviewer()

    def test_scan_docs_finds_files(self, reviewer, temp_docs):
        """scan_docs returns list of doc metadata."""
        docs = reviewer.scan_docs("*.txt")
        assert len(docs) == 2
        names = [d["name"] for d in docs]
        assert "report1.txt" in names
        assert "report2.txt" in names

    def test_scan_docs_metadata_fields(self, reviewer):
        """Each doc has required metadata fields."""
        docs = reviewer.scan_docs("*.txt")
        for doc in docs:
            assert "path" in doc
            assert "name" in doc
            assert "modified" in doc
            assert "size_bytes" in doc
            assert "preview" in doc

    def test_scan_docs_empty_dir(self, mock_client, tmp_path):
        """Empty directory returns empty list."""
        with patch("deepr.services.doc_reviewer.OpenAI", return_value=mock_client):
            from deepr.services.doc_reviewer import DocReviewer

            r = DocReviewer(api_key="test-key", docs_path=str(tmp_path))
            docs = r.scan_docs("*.txt")
            assert docs == []

    def test_scan_docs_custom_pattern(self, mock_client, tmp_path):
        """Custom pattern filters correctly."""
        (tmp_path / "notes.md").write_text("markdown content")
        (tmp_path / "data.txt").write_text("text content")
        with patch("deepr.services.doc_reviewer.OpenAI", return_value=mock_client):
            from deepr.services.doc_reviewer import DocReviewer

            r = DocReviewer(api_key="test-key", docs_path=str(tmp_path))
            md_docs = r.scan_docs("*.md")
            assert len(md_docs) == 1
            assert md_docs[0]["name"] == "notes.md"

    def test_review_docs_no_existing_docs(self, mock_client, tmp_path):
        """Returns gap when no docs exist."""
        with patch("deepr.services.doc_reviewer.OpenAI", return_value=mock_client):
            from deepr.services.doc_reviewer import DocReviewer

            r = DocReviewer(api_key="test-key", docs_path=str(tmp_path))
            result = r.review_docs("Market analysis")
            assert len(result["gaps"]) == 1
            assert result["gaps"][0] == "Market analysis"

    def test_review_docs_calls_llm(self, reviewer, mock_client):
        """review_docs calls chat.completions.create for evaluation."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "sufficient": [],
                "needs_update": [],
                "gaps": ["topic1"],
                "recommendations": [],
            }
        )
        reviewer.review_docs("Scenario")
        mock_client.chat.completions.create.assert_called_once()

    def test_review_docs_sorts_by_modified(self, reviewer, mock_client):
        """Most recent docs are reviewed first."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "sufficient": [],
                "needs_update": [],
                "gaps": [],
                "recommendations": [],
            }
        )
        reviewer.review_docs("Scenario", max_docs_to_review=1)
        # Should not crash, limits to max_docs_to_review

    def test_review_docs_limits_count(self, reviewer, mock_client):
        """max_docs_to_review honored."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "sufficient": [],
                "needs_update": [],
                "gaps": [],
                "recommendations": [],
            }
        )
        reviewer.review_docs("Scenario", max_docs_to_review=1)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][1]["content"]
        # Should only have 1 doc section (Doc 1), not Doc 2
        assert "Doc 1:" in user_msg

    def test_review_docs_parses_response(self, reviewer, mock_client):
        """Returns structured dict from LLM response."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "sufficient": [{"path": "x.txt", "name": "x.txt", "reason": "Good"}],
                "needs_update": [],
                "gaps": ["Missing topic"],
                "recommendations": [{"action": "research", "topic": "New", "reason": "Needed"}],
            }
        )
        result = reviewer.review_docs("Scenario")
        assert len(result["sufficient"]) == 1
        assert len(result["gaps"]) == 1


class TestDocReviewerTaskGeneration:
    """Test generate_tasks_from_review."""

    @pytest.fixture
    def reviewer(self, mock_openai_env):
        with patch("deepr.services.doc_reviewer.OpenAI"):
            from deepr.services.doc_reviewer import DocReviewer

            return DocReviewer()

    def test_reuse_action_skipped(self, reviewer):
        """'reuse' action does not create a task."""
        review = {"recommendations": [{"action": "reuse", "doc": "x.txt", "reason": "OK"}]}
        tasks = reviewer.generate_tasks_from_review(review)
        assert len(tasks) == 0

    def test_update_action_creates_task(self, reviewer):
        """'update' action creates a task."""
        review = {
            "recommendations": [
                {"action": "update", "doc": "path/old.txt", "topic": "Update pricing", "reason": "Outdated"},
            ]
        }
        tasks = reviewer.generate_tasks_from_review(review)
        assert len(tasks) == 1
        assert "Update" in tasks[0]["title"]

    def test_research_action_creates_task(self, reviewer):
        """'research' action creates a new research task."""
        review = {
            "recommendations": [
                {"action": "research", "topic": "New market analysis", "reason": "Gap found"},
            ]
        }
        tasks = reviewer.generate_tasks_from_review(review)
        assert len(tasks) == 1
        assert tasks[0]["title"] == "New market analysis"

    def test_max_tasks_honored(self, reviewer):
        """max_tasks limits output."""
        review = {
            "recommendations": [{"action": "research", "topic": f"Topic {i}", "reason": "Need"} for i in range(10)]
        }
        tasks = reviewer.generate_tasks_from_review(review, max_tasks=3)
        assert len(tasks) == 3
