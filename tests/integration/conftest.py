"""Gate the integration suite behind an explicit live opt-in.

Integration tests exercise real provider APIs (and some make live, paid
calls). On a machine without API keys they fail wholesale, and at least one
historically hung forever. CI runs only `tests/unit/`, so this directory is
opt-in everywhere: it runs only when DEEPR_RUN_LIVE_TESTS=1 is set, matching
the double opt-in already used by the Azure live tests. A bare `pytest` from
a fresh checkout therefore skips this directory cleanly instead of failing
or hanging.

Set DEEPR_RUN_LIVE_TESTS=1 (plus the relevant provider keys) to run them.
"""

import os

import pytest

_RUN_LIVE = os.getenv("DEEPR_RUN_LIVE_TESTS") == "1"
_INTEGRATION_DIR = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip everything under tests/integration/ unless live tests are opted in."""
    if _RUN_LIVE:
        return
    skip_marker = pytest.mark.skip(
        reason="integration tests require DEEPR_RUN_LIVE_TESTS=1 (real provider keys; some make live calls)"
    )
    for item in items:
        if str(item.fspath).startswith(_INTEGRATION_DIR):
            item.add_marker(skip_marker)
