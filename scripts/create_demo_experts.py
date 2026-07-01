"""Create demo experts for the web dashboard ($0 cost, no API calls)."""

from datetime import UTC, datetime, timedelta

from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore
from deepr.experts.synthesis import KnowledgeGap, Worldview

store = ExpertStore()

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
        "knowledge_gaps": [
            {
                "topic": "Regional adaptation cost curves",
                "questions": [
                    "Which coastal adaptation strategies have verified lifecycle cost data by region?",
                    "Where do managed retreat assumptions diverge between public and private models?",
                ],
                "priority": 4,
            },
            {
                "topic": "Methane mitigation verification",
                "questions": [
                    "Which satellite methane datasets agree on super-emitter persistence?",
                    "How should reported abatement claims be cross-checked against atmospheric observations?",
                ],
                "priority": 3,
            },
        ],
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
        "knowledge_gaps": [
            {
                "topic": "Async cancellation safety",
                "questions": [
                    "Which Tokio primitives are cancel-safe across select loops?",
                    "Where do dropped futures still leave durable side effects?",
                ],
                "priority": 5,
            },
            {
                "topic": "Unsafe abstraction audits",
                "questions": [
                    "Which unsafe blocks rely on aliasing or pinning invariants?",
                    "What property tests best expose soundness boundary regressions?",
                ],
                "priority": 4,
            },
            {
                "topic": "Backpressure design",
                "questions": [
                    "Which tower layers preserve backpressure under bursty workloads?",
                    "How should tracing surface queue saturation without log storms?",
                ],
                "priority": 3,
            },
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
        "knowledge_gaps": [
            {
                "topic": "External validity of nudges",
                "questions": [
                    "Which choice-architecture results survive replication across cultures?",
                    "How large is the measured decay when interventions move from lab to field?",
                ],
                "priority": 4,
            },
            {
                "topic": "AI-mediated decision aids",
                "questions": [
                    "When do recommendation systems amplify status-quo bias?",
                    "Which disclosure formats measurably improve calibrated trust?",
                ],
                "priority": 3,
            },
        ],
        "total_research_cost": 1.20,
        "conversations": 5,
        "domain_velocity": "slow",
        "days_old": 60,
        "last_update_days": 12,
    },
]

now = datetime.now(UTC)

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

    gaps = [
        KnowledgeGap(
            topic=gap["topic"],
            questions=gap["questions"],
            priority=gap["priority"],
            identified_at=now - timedelta(days=demo["last_update_days"]),
        )
        for gap in demo["knowledge_gaps"]
    ]
    worldview = Worldview(
        expert_name=demo["name"],
        domain=demo["domain"],
        knowledge_gaps=gaps,
        last_synthesis=now - timedelta(days=demo["last_update_days"]),
        synthesis_count=len(demo["research_jobs"]),
    )
    worldview.save(store.get_knowledge_dir(demo["name"]) / "worldview.json")
    print(f"  Created '{demo['name']}' ({len(demo['source_files'])} docs, ${demo['total_research_cost']})")

print("Done.")
