"""Print a read-only summary of the canonical append-only cost ledger."""

from __future__ import annotations

from deepr.observability.cost_ledger import CostLedger


def main() -> None:
    """Show recent canonical events and the exact all-time total."""
    ledger = CostLedger()
    events = ledger.get_events()

    print(f"Canonical ledger: {ledger.ledger_path}")
    print("Recent events:")
    if not events:
        print("  No cost events recorded.")
    for event in events[-10:][::-1]:
        timestamp = event.timestamp.isoformat(timespec="seconds")
        label = f"{event.operation} [{event.provider}]"
        print(f"  {timestamp} | {label[:52]:52} | ${event.cost_usd:.6f}")

    total = sum(event.cost_usd for event in events)
    print(f"\nAll-time canonical total: ${total:.6f}")


if __name__ == "__main__":
    main()
