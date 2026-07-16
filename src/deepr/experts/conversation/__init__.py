"""Protocol-neutral durable expert conversations.

Package map:

- ``models``: validated requests, results, ids, hashes, and typed errors.
- ``context``: deterministic bounded context assembly.
- ``database`` and ``schema``: SQLite connection, transaction, and migration lifecycle.
- ``reservations``: append-before-dispatch admission, replay, and resume.
- ``store`` and ``transitions``: event, projection, content, idempotency,
  recovery, and post-execution lease state.
- ``service``: injected-executor orchestration with no protocol assumptions.
- ``snapshots``: bounded immutable packets compiled from canonical expert state.
- ``local_executor``: verified local Ollama turns with no tools or fallback.
"""

from deepr.experts.conversation.local_executor import LocalOllamaConversationExecutor
from deepr.experts.conversation.models import (
    BackendSelection,
    ConversationBounds,
    ConversationContinueRequest,
    ConversationOperationResult,
    ConversationResumeRequest,
    ConversationStartRequest,
    ConversationState,
    ExpertSnapshotInput,
    TurnExecutionResult,
    TurnState,
    TurnUsage,
)
from deepr.experts.conversation.service import ExpertConversationService, ExpertConversationTurnExecutor
from deepr.experts.conversation.store import ExpertConversationStore

__all__ = [
    "BackendSelection",
    "ConversationBounds",
    "ConversationContinueRequest",
    "ConversationOperationResult",
    "ConversationResumeRequest",
    "ConversationStartRequest",
    "ConversationState",
    "ExpertConversationService",
    "ExpertConversationStore",
    "ExpertConversationTurnExecutor",
    "ExpertSnapshotInput",
    "LocalOllamaConversationExecutor",
    "TurnExecutionResult",
    "TurnState",
    "TurnUsage",
]
