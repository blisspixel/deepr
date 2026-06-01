"""Regression test: expert-conversation GET/DELETE must reject traversal session_ids.

session_id flows into a filesystem path; a value outside [\\w-] (e.g. containing
'.' or path separators) must be rejected with 400 before any file access.
"""

from __future__ import annotations

import pytest

flask_app = pytest.importorskip("flask")  # web extra may be absent
from deepr.web.app import app  # noqa: E402


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.mark.parametrize("bad_id", ["foo..bar", "a.b", "x..y", "with.dot"])
def test_get_conversation_rejects_traversal_session_id(client, bad_id):
    resp = client.get(f"/api/experts/test/conversations/{bad_id}")
    # The traversal guard returns 400. (Never 200/404-from-file or 500.)
    assert resp.status_code == 400


@pytest.mark.parametrize("bad_id", ["foo..bar", "a.b"])
def test_delete_conversation_rejects_traversal_session_id(client, bad_id):
    resp = client.delete(f"/api/experts/test/conversations/{bad_id}")
    assert resp.status_code == 400
