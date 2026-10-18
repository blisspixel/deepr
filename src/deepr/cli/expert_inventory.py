"""One stored expert inventory for human and JSON inspection."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from deepr.cli.colors import print_next
from deepr.experts.claim_inventory import format_knowledge_status, read_claim_inventory


def expert_inventory() -> dict[str, Any]:
    from deepr.experts.profile import ExpertStore

    rows = []
    for expert in ExpertStore().list_all():
        inventory = read_claim_inventory(expert)
        rows.append(
            {
                "name": expert.name,
                "description": expert.description,
                "claims": inventory.claim_count,
                "average_claim_confidence": inventory.avg_confidence,
                "documents": expert.total_documents,
                "conversations": expert.conversations,
                "research_jobs": expert.research_triggered,
                "research_cost_usd": expert.total_research_cost,
                "created_at": expert.created_at.isoformat(),
                "updated_at": expert.updated_at.isoformat(),
                "knowledge_status": format_knowledge_status(expert, inventory),
            }
        )
    return {"schema_version": "deepr-expert-inventory-v1", "experts": rows, "count": len(rows), "cost_usd": 0.0}


def render_expert_inventory(payload: dict[str, Any], console: Console) -> None:
    console.print("Domain Experts", style="bold")
    if not payload["experts"]:
        console.print("No experts found.")
        print_next('deepr expert make "Expert Name" --local', target=console)
        return
    console.print(f"Found {payload['count']} expert(s):\n")
    for row in payload["experts"]:
        lines = [f"  Name: {row['name']}"]
        if row["description"]:
            lines.append(f"    Description: {row['description']}")
        confidence = row["average_claim_confidence"]
        suffix = f", avg conf {confidence:.2f}" if confidence is not None and row["claims"] else ""
        lines.extend(
            [
                f"    Claims: {row['claims']}{suffix}",
                f"    Documents: {row['documents']}",
                f"    Conversations: {row['conversations']}",
            ]
        )
        if row["research_jobs"] > 0:
            lines.append(f"    Research: {row['research_jobs']} jobs (${row['research_cost_usd']:.2f})")
        created, updated = row["created_at"].split("T")[0], row["updated_at"].split("T")[0]
        lines.append(f"    Created: {created}" + (f", Updated: {updated}" if created != updated else ""))
        lines.append(f"    Knowledge: {row['knowledge_status']}")
        console.print("\n".join(lines) + "\n", markup=False)
    console.print('Usage:\n  deepr expert consult "your question" --expert "<name>" --local')
    console.print(
        "Claims are the belief-store inventory, not an expertise grade. Documents: 0 with Claims > 0 is normal after absorb --file."
    )
