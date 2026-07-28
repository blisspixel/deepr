"""CLI coverage for offline provider billing reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from deepr.cli.main import cli


def _write_bill(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "deepr-provider-billing-import-v1",
                "kind": "deepr.costs.provider_billing_import",
                "provider": "openai",
                "billing_scope": {"scope_ref": "project-primary", "account_id": "account-1"},
                "statement": {
                    "statement_id": "statement-1",
                    "status": "final",
                    "complete": True,
                    "period_start": "2026-07-01T00:00:00+00:00",
                    "period_end": "2026-08-01T00:00:00+00:00",
                    "currency": "USD",
                    "source_posture": "operator_normalized",
                    "net_total_usd": "0.500000",
                },
                "lines": [
                    {
                        "line_id": "line-1",
                        "category": "metered_api",
                        "capacity_class": "api_metered",
                        "usage_start": "2026-07-01T01:00:00+00:00",
                        "usage_end": "2026-07-01T01:01:00+00:00",
                        "charge_usd": "0.500000",
                        "credit_usd": "0",
                        "adjustment_usd": "0",
                        "tax_usd": "0",
                        "net_usd": "0.500000",
                        "provider_http_request_id": "req-unmatched",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_reconcile_billing_json_preview_is_nonzero_for_drift(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    _write_bill(source)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["costs", "reconcile-billing", str(source), "--json", "--ledger-path", str(tmp_path / "ledger.jsonl")],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "drift"
    assert payload["zero_network_calls"] is True
    assert payload["zero_provider_calls"] is True


def test_reconcile_billing_human_preview_states_write_free_mode(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    _write_bill(source)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["costs", "reconcile-billing", str(source), "--ledger-path", str(tmp_path / "ledger.jsonl")],
    )

    assert result.exit_code == 1
    assert "write-free preview" in result.output
    assert "No network or provider call was made" in result.output
    assert "wrote no files" in result.output


def test_reconcile_billing_rejects_expected_scope_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    _write_bill(source)

    result = CliRunner().invoke(
        cli,
        ["costs", "reconcile-billing", str(source), "--expect-scope-ref", "another-project"],
    )

    assert result.exit_code == 1
    assert "expected scope" in result.output
