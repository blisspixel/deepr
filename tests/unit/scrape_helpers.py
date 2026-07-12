"""Shared helpers for scraper unit tests."""

from __future__ import annotations

from requests import Response

SCRAPE_HTML = """
<html>
<head><title>Example Research Page</title></head>
<body>
    <main>
        <h1>Example Domain</h1>
        <p>Example content for deterministic scraper tests.</p>
        <a href="/about">About</a>
    </main>
</body>
</html>
"""


def make_scrape_response(url: str = "https://example.com", html: str = SCRAPE_HTML) -> Response:
    response = Response()
    response.status_code = 200
    response.url = url
    response._content = html.encode("utf-8")
    response._content_consumed = True
    response.encoding = "utf-8"
    return response
