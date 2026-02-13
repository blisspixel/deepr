"""Create demo experts for the web dashboard ($0 cost, no API calls)."""

from datetime import datetime, timedelta, timezone

from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore

store = ExpertStore("data/experts")

demos = [
    {
        "name": "Climate Science",
        "description": "IPCC reports, carbon budgets, climate modeling, and emissions pathways",
        "domain": "climate-science",
        "source_files": [
            "ipcc-ar6-wg1-summary.pdf",
            "ipcc-ar6-wg2-summary.pdf",
            "ipcc-ar6-wg3-summary.pdf",
            "global-carbon-budget-2024.pdf",
            "nasa-giss-temperature-data.csv",
            "noaa-co2-mauna-loa.csv",
            "nature-climate-tipping-points.pdf",
            "science-carbon-removal-review.pdf",
            "iea-net-zero-2050.pdf",
            "unep-emissions-gap-2024.pdf",
            "world-bank-climate-finance.pdf",
            "methane-tracker-2024.pdf",
        ],
        "research_jobs": ["job-cc-001", "job-cc-002", "job-cc-003", "job-cc-004"],
        "total_research_cost": 3.42,
        "conversations": 8,
        "domain_velocity": "medium",
        "days_old": 45,
        "last_update_days": 3,
    },
    {
        "name": "Rust Systems Programming",
        "description": "Tokio async runtime, ownership model, unsafe patterns, and systems design",
        "domain": "systems-programming",
        "source_files": [
            "rust-book-ch1-ch5.md",
            "rust-book-ch6-ch10.md",
            "rust-book-ch11-ch15.md",
            "rust-book-ch16-ch20.md",
            "tokio-tutorial-full.md",
            "tokio-internals-blog.md",
            "async-rust-book.md",
            "rustonomicon-unsafe.md",
            "serde-guide.md",
            "rust-perf-book.md",
            "crossbeam-docs.md",
            "rayon-parallel-iterators.md",
            "rust-embedded-book.md",
            "pin-unpin-explained.md",
            "rust-atomics-locks-book.md",
            "tower-service-patterns.md",
            "hyper-internals.md",
            "tracing-subscriber-guide.md",
        ],
        "research_jobs": [
            "job-rs-001",
            "job-rs-002",
            "job-rs-003",
            "job-rs-004",
            "job-rs-005",
            "job-rs-006",
            "job-rs-007",
        ],
        "total_research_cost": 7.85,
        "conversations": 23,
        "domain_velocity": "fast",
        "days_old": 30,
        "last_update_days": 1,
    },
    {
        "name": "Behavioral Economics",
        "description": "Kahneman & Tversky, nudge theory, prospect theory, and choice architecture",
        "domain": "behavioral-economics",
        "source_files": [
            "thinking-fast-slow-notes.md",
            "nudge-thaler-sunstein.md",
            "prospect-theory-original.pdf",
            "misbehaving-thaler.md",
            "predictably-irrational-ariely.md",
            "noise-kahneman.md",
            "judgment-uncertainty-heuristics.pdf",
            "sunk-cost-fallacy-review.pdf",
            "choice-architecture-survey.pdf",
        ],
        "research_jobs": ["job-be-001", "job-be-002"],
        "total_research_cost": 1.20,
        "conversations": 5,
        "domain_velocity": "slow",
        "days_old": 60,
        "last_update_days": 12,
    },
]

now = datetime.now(timezone.utc)

for demo in demos:
    if store.exists(demo["name"]):
        print(f"  Skipping '{demo['name']}' (already exists)")
        continue

    profile = ExpertProfile(
        name=demo["name"],
        vector_store_id="",
        description=demo["description"],
        domain=demo["domain"],
        created_at=now - timedelta(days=demo["days_old"]),
        updated_at=now - timedelta(days=demo["last_update_days"]),
        source_files=demo["source_files"],
        research_jobs=demo["research_jobs"],
        total_documents=len(demo["source_files"]),
        total_research_cost=demo["total_research_cost"],
        conversations=demo["conversations"],
        domain_velocity=demo["domain_velocity"],
    )
    store.save(profile)
    print(f"  Created '{demo['name']}' ({len(demo['source_files'])} docs, ${demo['total_research_cost']})")

print("Done.")
