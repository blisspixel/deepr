"""Fail-closed request contract for browser expert chat."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from deepr.experts.commands import ChatMode

_SESSION_ID_RE = re.compile(r"^[\w-]{1,128}$")
_EXPERT_NAME_RE = re.compile(r"^[\w \-().,']+$")


class BrowserChatContractError(ValueError):
    """A public browser chat request failed deterministic validation."""

    def __init__(self, message: str, *, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Return the stable public error payload shared by HTTP and Socket.IO."""
        return {
            "error": str(self),
            "error_code": self.code,
            "retryable": False,
        }


@dataclass(frozen=True)
class BrowserExpertChatRequest:
    """Parsed browser chat side-effect contract."""

    backend: str
    budget: float
    chat_mode: ChatMode
    session_id: str | None


def parse_browser_expert_name(value: Any) -> str:
    """Validate the Socket.IO expert identity before provider construction."""
    if not isinstance(value, str):
        raise BrowserChatContractError(
            "expert_name is required.",
            code="invalid_chat_request",
        )
    expert_name = value.strip()
    if (
        not expert_name
        or len(expert_name) > 200
        or ".." in expert_name
        or "/" in expert_name
        or "\\" in expert_name
        or _EXPERT_NAME_RE.fullmatch(expert_name) is None
    ):
        raise BrowserChatContractError(
            "expert_name contains unsupported characters.",
            code="invalid_chat_expert_name",
        )
    return expert_name


def parse_browser_expert_chat_request(data: Any, *, max_budget: float) -> BrowserExpertChatRequest:
    """Parse browser chat controls before provider or expert construction."""
    if not isinstance(data, dict):
        raise BrowserChatContractError(
            "Browser expert chat requires a JSON object.",
            code="invalid_chat_request",
        )

    backend = data.get("backend")
    if backend != "api":
        raise BrowserChatContractError(
            "Browser expert chat supports only backend=api. Use CLI or MCP for local or plan chat.",
            code="unsupported_chat_backend",
        )

    if data.get("allow_metered_api") is not True or data.get("confirm_metered_cost") is not True:
        raise BrowserChatContractError(
            "Metered browser chat requires explicit API and cost confirmation.",
            code="metered_chat_not_confirmed",
            status_code=402,
        )

    if isinstance(max_budget, bool) or not isinstance(max_budget, (int, float)) or not math.isfinite(max_budget):
        raise BrowserChatContractError(
            "Browser chat budget controls are unavailable.",
            code="chat_budget_unavailable",
            status_code=503,
        )
    ceiling = float(max_budget)
    if ceiling <= 0:
        raise BrowserChatContractError(
            "Browser chat budget controls are unavailable.",
            code="chat_budget_unavailable",
            status_code=503,
        )

    raw_budget = data.get("budget")
    if (
        isinstance(raw_budget, bool)
        or not isinstance(raw_budget, (int, float))
        or not math.isfinite(raw_budget)
        or raw_budget <= 0
        or raw_budget > ceiling
    ):
        raise BrowserChatContractError(
            f"budget must be a finite number greater than 0 and no more than {ceiling:.2f}.",
            code="invalid_chat_budget",
        )

    raw_mode = data.get("chat_mode")
    try:
        chat_mode = ChatMode(raw_mode)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(mode.value for mode in ChatMode)
        raise BrowserChatContractError(
            f"chat_mode must be one of: {choices}.",
            code="invalid_chat_mode",
        ) from exc

    raw_session_id = data.get("session_id")
    session_id = None
    if raw_session_id is not None:
        if not isinstance(raw_session_id, str) or not _SESSION_ID_RE.fullmatch(raw_session_id):
            raise BrowserChatContractError(
                "session_id contains unsupported characters.",
                code="invalid_chat_session_id",
            )
        session_id = raw_session_id

    return BrowserExpertChatRequest(
        backend=backend,
        budget=float(raw_budget),
        chat_mode=chat_mode,
        session_id=session_id,
    )
