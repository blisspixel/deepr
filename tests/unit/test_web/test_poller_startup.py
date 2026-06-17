"""Regression tests for the web background poller startup hook."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("flask")

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

import deepr.web.app as web_app


def test_testing_mode_does_not_start_background_poller(monkeypatch):
    monkeypatch.setitem(web_app.app.config, "TESTING", True)
    monkeypatch.setattr(web_app, "_poller_started", False)

    started = []

    class DummyThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started.append(self.kwargs)

    monkeypatch.setattr(web_app.threading, "Thread", DummyThread)

    web_app._start_poller()

    assert web_app._poller_started is False
    assert started == []
