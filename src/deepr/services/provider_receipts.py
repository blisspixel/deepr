"""Safe extraction of non-secret provider billing receipt identifiers."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderReceiptIdentifiers:
    """Provider identifiers that can join local settlement to billing evidence."""

    http_request_id: str = ""
    object_id: str = ""


def _optional_declared_attribute(value: object, name: str) -> object | None:
    try:
        inspect.getattr_static(value, name)
    except AttributeError:
        return None
    try:
        return getattr(value, name, None)
    except Exception:
        return None


def _known_value(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        try:
            return value.get(name)
        except Exception:
            return None
    return _optional_declared_attribute(value, name)


def _safe_identifier(value: object | None) -> str:
    if not isinstance(value, str):
        return ""
    identifier = value.strip()
    if not identifier or len(identifier) > 256:
        return ""
    if any(ord(character) < 33 or ord(character) > 126 for character in identifier):
        return ""
    return identifier


def _safe_header_name(value: object) -> str:
    try:
        return str(value).strip().lower()
    except Exception:
        return ""


def merge_provider_receipt_identifiers(
    first: ProviderReceiptIdentifiers,
    second: ProviderReceiptIdentifiers,
) -> ProviderReceiptIdentifiers:
    """Merge receipt identifiers without replacing earlier stronger evidence."""
    return ProviderReceiptIdentifiers(
        http_request_id=first.http_request_id or second.http_request_id,
        object_id=first.object_id or second.object_id,
    )


def _header_request_id(headers: object | None) -> str:
    if not isinstance(headers, Mapping):
        return ""
    accepted = {
        "request-id",
        "x-amzn-requestid",
        "x-goog-request-id",
        "x-ms-request-id",
        "x-request-id",
    }
    try:
        for index, (name, value) in enumerate(headers.items()):
            if index >= 64:
                break
            normalized_name = _safe_header_name(name)
            if normalized_name in accepted:
                identifier = _safe_identifier(value)
                if identifier:
                    return identifier
    except Exception:
        return ""
    return ""


def extract_provider_receipt_identifiers(value: object) -> ProviderReceiptIdentifiers:
    """Extract bounded receipt IDs without probing undeclared dynamic fields."""
    identifiers = ProviderReceiptIdentifiers()
    pending: list[object] = [value]
    seen: set[int] = set()
    while pending and len(seen) < 8:
        current = pending.pop(0)
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)

        http_request_id = ""
        for name in ("_request_id", "provider_request_id", "request_id"):
            http_request_id = _safe_identifier(_known_value(current, name))
            if http_request_id:
                break
        if not http_request_id:
            http_request_id = _header_request_id(_known_value(current, "headers"))
        object_id = _safe_identifier(_known_value(current, "id"))
        identifiers = merge_provider_receipt_identifiers(
            identifiers,
            ProviderReceiptIdentifiers(http_request_id=http_request_id, object_id=object_id),
        )

        nested_response = _known_value(current, "response")
        if nested_response is not None and not isinstance(nested_response, (str, bytes, int, float, bool)):
            pending.append(nested_response)
        if isinstance(current, BaseException):
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)
    return identifiers


def provider_receipt_settlement_fields(
    *,
    client_correlation_id: str,
    identifiers: ProviderReceiptIdentifiers,
) -> tuple[str, dict[str, str]]:
    """Build the legacy request field and typed receipt metadata."""
    metadata: dict[str, str] = {}
    safe_correlation_id = _safe_identifier(client_correlation_id)
    if safe_correlation_id:
        metadata["client_correlation_id"] = safe_correlation_id
    if identifiers.http_request_id:
        metadata["provider_http_request_id"] = identifiers.http_request_id
    if identifiers.object_id:
        metadata["provider_object_id"] = identifiers.object_id
    request_id = identifiers.http_request_id or identifiers.object_id
    return request_id, metadata


__all__ = [
    "ProviderReceiptIdentifiers",
    "extract_provider_receipt_identifiers",
    "merge_provider_receipt_identifiers",
    "provider_receipt_settlement_fields",
]
