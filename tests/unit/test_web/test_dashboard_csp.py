"""Production theme repairs retain the existing browser security boundary."""

import pytest

from deepr.web import app as web_app


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_dashboard_keeps_self_hosted_script_and_font_policy(scheme, monkeypatch):
    if web_app.limiter is not None:
        monkeypatch.setattr(web_app.limiter, "enabled", False)
    response = web_app.app.test_client().get("/api/health", base_url=f"{scheme}://localhost")
    assert response.status_code == 200
    directives = dict(item.strip().split(" ", 1) for item in response.headers["Content-Security-Policy"].split(";"))
    assert directives["script-src"] == "'self'"
    assert directives["font-src"] == "'self'"
    assert directives["object-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert ("Strict-Transport-Security" in response.headers) == (scheme == "https")
