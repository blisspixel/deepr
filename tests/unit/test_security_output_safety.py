"""Tests for derived host-facing output safety."""

from __future__ import annotations

import json

from deepr.security.output_safety import sanitize_host_facing_payload


def test_host_payload_redacts_recognized_credentials_recursively():
    secrets = (
        "sk-proj-abcdefghijk123456789",
        "bearer-secret-value",
        "signed-query-value",
        "url-password",
        "eyJabcdefghijk.abcdefghijk.signature",
    )
    payload = {
        "provider": secrets[0],
        "authorization": f"Authorization: Bearer {secrets[1]}",
        "links": [
            f"https://example.test/result?X-Goog-Signature={secrets[2]}&safe=yes",
            f"https://user:{secrets[3]}@example.test/path",
            "https://example.test/result?sig=sas-secret&safe=yes",
        ],
        "jwt": secrets[4],
        "safe": "ordinary diagnostic text",
    }

    sanitized = sanitize_host_facing_payload(payload)
    encoded = json.dumps(sanitized)

    assert all(secret not in encoded for secret in secrets)
    assert sanitized["safe"] == "ordinary diagnostic text"
    assert "safe=yes" in encoded
    assert "sas-secret" not in encoded


def test_host_payload_preserves_noncredential_identifiers_and_numbers():
    payload = {"run_id": "loop_123", "topic": "API key rotation policy", "count": 3}

    assert sanitize_host_facing_payload(payload) == payload


def test_host_payload_redacts_prefixed_environment_credentials():
    values = {
        "openai": "OPENAI_API_KEY=opaque-openai-value",
        "azure": "AZURE_OPENAI_KEY=0123456789abcdef0123456789abcdef",
        "aws": "AWS_SECRET_ACCESS_KEY=aws-secret-value",
        "slack": "SLACK_BOT_TOKEN=xoxb-opaque-slack-value",
    }

    sanitized = sanitize_host_facing_payload(values)

    assert all("[REDACTED]" in value for value in sanitized.values())
    assert all(raw.split("=", 1)[1] not in str(sanitized) for raw in values.values())


def test_host_payload_preserves_noncredential_uppercase_key_and_token_fields():
    payload = {
        "mapping": {
            "SORT_KEY": "created_at",
            "PARTITION_KEY": "customer_id",
            "CACHE_KEY": "users_by_id",
            "NEXT_PAGE_TOKEN": "cursor_17",
        },
        "diagnostic": ("SORT_KEY=created_at PARTITION_KEY=customer_id CACHE_KEY=users_by_id NEXT_PAGE_TOKEN=cursor_17"),
    }

    assert sanitize_host_facing_payload(payload) == payload


def test_host_payload_redacts_structured_provider_and_header_credentials():
    payload = {
        "provider": {
            "OPENAI_API_KEY": "opaque-openai-value",
            "AWS_SECRET_ACCESS_KEY": "opaque-aws-value",
        },
        "headers": {
            "X-Goog-Api-Key": "opaque-google-value",
            "Proxy-Authorization": "opaque-proxy-value",
            "Cookie": "opaque-session-value",
        },
        "input_tokens": 12,
        "cookie": "chocolate chip",
    }

    sanitized = sanitize_host_facing_payload(payload)

    assert sanitized["provider"] == {
        "OPENAI_API_KEY": "[REDACTED]",
        "AWS_SECRET_ACCESS_KEY": "[REDACTED]",
    }
    assert sanitized["headers"] == {
        "X-Goog-Api-Key": "[REDACTED]",
        "Proxy-Authorization": "[REDACTED]",
        "Cookie": "[REDACTED]",
    }
    assert sanitized["input_tokens"] == 12
    assert sanitized["cookie"] == "chocolate chip"


def test_host_payload_preserves_benign_secret_vocabulary():
    payload = {
        "recipe": "The recipe secret: cinnamon",
        "fermentation": "The recipe secret: fermentation",
        "example": "password=incorrect",
        "economics": "access token: economy",
        "work": "access token: productivity",
        "quoted_recipe": 'The recipe secret: "fermentation takes time"',
        "quoted_economics": 'access token: "a unit of economic measurement"',
    }

    assert sanitize_host_facing_payload(payload) == payload


def test_host_payload_redacts_quoted_multiword_passwords():
    secrets = (
        "correct horse battery staple",
        "abcdefghijklmnop",
        "correcthorsebatterystaple",
        "abcdefghijklmnopqrstuvwx",
    )
    payload = {
        "quoted": f'login rejected for password="{secrets[0]}"',
        "alphabetic_token": f"token={secrets[1]}",
        "alphabetic_password": f"password={secrets[2]}",
        "alphabetic_api_key": f"api_key={secrets[3]}",
    }

    sanitized = sanitize_host_facing_payload(payload)

    assert all(secret not in str(sanitized) for secret in secrets)
    assert "password=[REDACTED]" in sanitized["quoted"]


def test_host_payload_redacts_values_in_typed_secret_fields():
    payload = {"password": "incorrect", "client_secret": "short", "topic": "secret: cinnamon"}

    sanitized = sanitize_host_facing_payload(payload)

    assert sanitized == {"password": "[REDACTED]", "client_secret": "[REDACTED]", "topic": "secret: cinnamon"}


def test_host_payload_bounds_deeply_nested_content():
    payload: object = "visible only beyond the supported nesting depth"
    for _ in range(120):
        payload = {"child": payload}

    sanitized = sanitize_host_facing_payload(payload)

    current = sanitized
    traversed = 0
    while isinstance(current, dict):
        current = current["child"]
        traversed += 1
    assert traversed > 64
    assert current == "[CONTENT OMITTED: nesting limit exceeded]"
