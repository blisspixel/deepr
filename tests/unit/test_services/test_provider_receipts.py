"""Tests for non-secret provider billing receipt extraction."""

from collections.abc import Iterator, Mapping
from types import SimpleNamespace

from deepr.services.provider_receipts import (
    ProviderReceiptIdentifiers,
    extract_provider_receipt_identifiers,
    merge_provider_receipt_identifiers,
    provider_receipt_settlement_fields,
)


def test_direct_http_request_id_precedes_header_and_keeps_object_id() -> None:
    response = SimpleNamespace(
        _request_id="req-direct",
        id="response-object",
        headers={"x-request-id": "req-header"},
    )

    identifiers = extract_provider_receipt_identifiers(response)

    assert identifiers == ProviderReceiptIdentifiers(
        http_request_id="req-direct",
        object_id="response-object",
    )


def test_header_request_id_is_case_insensitive_and_bounded() -> None:
    identifiers = extract_provider_receipt_identifiers(
        {"headers": {"Content-Type": "application/json", "X-MS-REQUEST-ID": "azure-request"}}
    )

    assert identifiers.http_request_id == "azure-request"
    assert identifiers.object_id == ""


def test_nested_exception_response_and_cause_are_traversed() -> None:
    provider_error = RuntimeError("provider failed")
    provider_error.response = SimpleNamespace(  # type: ignore[attr-defined]
        id="error-object",
        headers={"x-request-id": "req-from-response"},
    )
    wrapper = RuntimeError("wrapped")
    wrapper.__cause__ = provider_error

    identifiers = extract_provider_receipt_identifiers(wrapper)

    assert identifiers.http_request_id == "req-from-response"
    assert identifiers.object_id == "error-object"


def test_undeclared_dynamic_attributes_are_never_evaluated() -> None:
    class DynamicObject:
        def __init__(self) -> None:
            self.reads: list[str] = []

        def __getattr__(self, name: str) -> object:
            self.reads.append(name)
            raise AssertionError(f"unexpected dynamic field read: {name}")

    value = DynamicObject()

    assert extract_provider_receipt_identifiers(value) == ProviderReceiptIdentifiers()
    assert value.reads == []


def test_invalid_identifiers_are_ignored_instead_of_entering_ledger_metadata() -> None:
    identifiers = extract_provider_receipt_identifiers(
        {
            "request_id": "contains whitespace",
            "id": "x" * 257,
        }
    )

    assert identifiers == ProviderReceiptIdentifiers()


def test_broken_provider_mappings_cannot_break_receipt_extraction() -> None:
    class BrokenMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError(f"provider mapping failed for {key}")

        def __iter__(self) -> Iterator[str]:
            raise RuntimeError("provider mapping iteration failed")

        def __len__(self) -> int:
            return 1

    assert extract_provider_receipt_identifiers(BrokenMapping()) == ProviderReceiptIdentifiers()


def test_merge_preserves_first_evidence_and_fills_missing_fields() -> None:
    merged = merge_provider_receipt_identifiers(
        ProviderReceiptIdentifiers(http_request_id="first-request"),
        ProviderReceiptIdentifiers(http_request_id="second-request", object_id="object-id"),
    )

    assert merged == ProviderReceiptIdentifiers(
        http_request_id="first-request",
        object_id="object-id",
    )


def test_settlement_fields_keep_http_and_object_ids_distinct() -> None:
    request_id, metadata = provider_receipt_settlement_fields(
        client_correlation_id="client-job",
        identifiers=ProviderReceiptIdentifiers(
            http_request_id="http-request",
            object_id="provider-object",
        ),
    )

    assert request_id == "http-request"
    assert metadata == {
        "client_correlation_id": "client-job",
        "provider_http_request_id": "http-request",
        "provider_object_id": "provider-object",
    }


def test_settlement_fields_drop_unsafe_client_correlation_id() -> None:
    request_id, metadata = provider_receipt_settlement_fields(
        client_correlation_id="unsafe correlation",
        identifiers=ProviderReceiptIdentifiers(),
    )

    assert request_id == ""
    assert metadata == {}
