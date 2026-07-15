"""Property checks for replay and bounded continuation invariants."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given, settings, strategies as st

from deepr.experts.conversation.models import ConversationContinueRequest, IdempotencyConflict
from deepr.experts.conversation.store import ExpertConversationStore
from tests.unit.conversation_fixtures import completed_result, start_request

_SAFE_KEYS = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,39}", fullmatch=True)
_MESSAGES = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=200).filter(str.strip)


def _database(tmp_path: Path, material: str) -> Path:
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return tmp_path / f"property-{digest}.db"


@settings(max_examples=20, deadline=None)
@given(key=_SAFE_KEYS, message=_MESSAGES)
def test_duplicate_start_never_creates_a_second_dispatch(key: str, message: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = ExpertConversationStore(_database(Path(directory), f"start:{key}:{message}"))
        request = start_request(idempotency_key=key, message=message)

        first = store.reserve_start(request)
        second = store.reserve_start(request)

        assert first.dispatch_required is True
        assert second.dispatch_required is False
        assert second.conversation_id == first.conversation_id
        assert second.turn_id == first.turn_id


@settings(max_examples=12, deadline=None)
@given(messages=st.lists(_MESSAGES, min_size=1, max_size=8, unique=True))
def test_versions_are_monotonic_and_recent_context_never_exceeds_six(messages: list[str]) -> None:
    material = "|".join(messages)
    with tempfile.TemporaryDirectory() as directory:
        store = ExpertConversationStore(_database(Path(directory), f"turns:{material}"))
        start = store.reserve_start(start_request(idempotency_key="property-start"))
        state = store.finalize_turn(start, completed_result())
        version = 2

        for index, message in enumerate(messages, start=2):
            lease = store.reserve_continue(
                ConversationContinueRequest(
                    owner_id="owner-a",
                    conversation_id=start.conversation_id,
                    expected_version=version,
                    idempotency_key=f"property-turn-{index}",
                    message=message,
                )
            )
            assert lease.projection_version == version + 1
            assert lease.execution_context is not None
            assert len(lease.execution_context.recent_turns) <= 6
            state = store.finalize_turn(lease, completed_result())
            version += 2
            assert state.conversation["version"] == version

        assert state.conversation["usage"]["turns_started"] == len(messages) + 1


@settings(max_examples=12, deadline=None)
@given(first=_MESSAGES, second=_MESSAGES.filter(str.strip))
def test_same_idempotency_key_with_different_material_never_replays(
    first: str,
    second: str,
) -> None:
    assume(first != second)
    with tempfile.TemporaryDirectory() as directory:
        store = ExpertConversationStore(_database(Path(directory), f"conflict:{first}:{second}"))
        store.reserve_start(start_request(idempotency_key="shared-key", message=first))

        with pytest.raises(IdempotencyConflict):
            store.reserve_start(start_request(idempotency_key="shared-key", message=second))
