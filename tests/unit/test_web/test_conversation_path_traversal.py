"""Regression test: expert-conversation GET/DELETE must reject traversal session_ids.

session_id flows into a filesystem path; a value outside [\\w-] (e.g. containing
'.' or path separators) must be rejected with 400 before any file access.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("flask")  # web extra may be absent

# Keep provider-backed submission out of this path-only test module.
# to be present (it is only stored, never called here). CI has no key, so set a
# dummy one before importing the app.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

from deepr.web.app import app


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
