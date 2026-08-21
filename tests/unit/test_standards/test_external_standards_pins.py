"""Offline integrity checks for external interoperability standards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from deepr.mcp.protocol_modern import MODERN_PROTOCOL_VERSION
from deepr.skills.contract import AGENT_SKILLS_REVISION, AGENT_SKILLS_SPEC_SHA256

ROOT = Path(__file__).resolve().parents[3]
PINS_PATH = ROOT / "docs" / "standards" / "pins.json"


def _pins() -> dict[str, object]:
    return json.loads(PINS_PATH.read_text(encoding="utf-8"))


def _urls(value: object) -> list[str]:
    if isinstance(value, dict):
        urls = [item for key, item in value.items() if key == "url" and isinstance(item, str)]
        for item in value.values():
            urls.extend(_urls(item))
        return urls
    if isinstance(value, list):
        return [url for item in value for url in _urls(item)]
    return []


def test_agent_plugin_schemas_match_immutable_upstream_bytes() -> None:
    standards = _pins()["standards"]
    agent_plugins = standards["agent_plugins"]

    assert agent_plugins["version"] == "1.0.0"
    assert agent_plugins["status"] == "Published"
    revision = agent_plugins["upstream_revision"]
    for artifact in agent_plugins["artifacts"]:
        path = ROOT / artifact["local_path"]
        payload = path.read_bytes()
        assert len(payload) == artifact["byte_length"]
        assert hashlib.sha256(payload).hexdigest() == artifact["sha256"]
        assert revision in artifact["url"]
        Draft202012Validator.check_schema(json.loads(payload))


def test_agent_skills_pin_matches_runtime_contract() -> None:
    standards = _pins()["standards"]
    pin = standards["agent_skills"]

    assert pin["status"] == "Published"
    assert pin["upstream_revision"] == AGENT_SKILLS_REVISION
    assert pin["specification"]["sha256"] == AGENT_SKILLS_SPEC_SHA256
    assert AGENT_SKILLS_REVISION in pin["specification"]["url"]


def test_mcp_pin_matches_blocking_modern_protocol() -> None:
    standards = _pins()["standards"]
    pin = standards["mcp"]

    assert pin["version"] == MODERN_PROTOCOL_VERSION == "2026-07-28"
    assert pin["status"] == "GA"
    assert pin["upstream_revision"] in pin["schema"]["url"]
    assert len(pin["schema"]["sha256"]) == 64


def test_pins_never_use_mutable_raw_main_urls() -> None:
    parsed_urls = [urlsplit(url) for url in _urls(_pins())]
    raw_urls = [url for url in parsed_urls if url.hostname == "raw.githubusercontent.com"]

    assert raw_urls
    assert all("main" not in PurePosixPath(url.path).parts for url in raw_urls)
