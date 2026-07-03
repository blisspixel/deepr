"""Ground-truth correctness eval for the grounding checker (`deepr eval grounding-correctness`).

The verification spine's whole promise is "a checker-verified belief is more
trustworthy than an unverified one." That promise is, by default, *asserted* -
nothing measures whether a SUPPORTED verdict is actually correct. This eval makes
it falsifiable: it runs the grounding checker over a curated golden set of
``(claim, evidence, label)`` triples with human ground-truth entailment labels
and measures whether the verdict matches the label.

The headline numbers:

- **support precision** - when the checker says SUPPORTED, how often is the
  evidence actually entailing (label == "supported")? This is the number that
  says "trust a verified belief."
- **false-support rate** - how often does it stamp SUPPORTED for evidence that
  contradicts or does not address the claim? The dangerous failure; low is safe.
- **support recall** - of the genuinely-entailed cases, how many did it confirm.
- **abstention rate** - could-not-verify responses (never invented verdicts).

AGENTIC_BALANCE: the model (checker) owns the entailment verdict (meaning); this
module is deterministic scoring of that verdict against human-curated ground
truth (form). The labels are human judgments, never a lexical rule. Agreement on
a bounded curated set is not proof of world-truth; the report discloses the set
size and framing so a number is never over-read.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GROUNDING_CORRECTNESS_SCHEMA_VERSION = "deepr-grounding-correctness-v1"
GROUNDING_CORRECTNESS_KIND = "deepr.eval.grounding_correctness"

# Ground-truth entailment labels. "supported": the evidence entails the claim;
# "contradicted": the evidence refutes it; "unrelated": the evidence does not
# address it. A correct checker returns supported=True only for "supported".
_LABELS = ("supported", "contradicted", "unrelated")

# A CheckVerdict-shaped result: .supported is True / False / None (could-not-verify).
GroundingVerdict = Any
GroundingChecker = Callable[[str, str], Awaitable[GroundingVerdict]]


@dataclass(frozen=True)
class GroundingCase:
    """One human-labeled claim/evidence entailment triple."""

    case_id: str
    claim: str
    evidence: str
    label: str

    def __post_init__(self) -> None:
        if self.label not in _LABELS:
            raise ValueError(f"label must be one of {_LABELS}, got {self.label!r}")
        if not self.claim.strip() or not self.evidence.strip():
            raise ValueError(f"case {self.case_id!r} needs a non-empty claim and evidence")


# The built-in golden set. Timeless, unambiguous entailment triples across mixed
# domains (science, geography, history, math, definitions), balanced across the
# three labels, curated so the correct verdict is not in dispute. Kept small and
# stable so the number is reproducible; extend via --cases for domain-specific runs.
DEFAULT_GROUNDING_CASES: tuple[GroundingCase, ...] = (
    # --- supported: evidence entails the claim ---
    GroundingCase(
        "sup-water-boil",
        "Water boils at 100 degrees Celsius at sea level.",
        "At standard atmospheric pressure (sea level), pure water boils at 100 C (212 F).",
        "supported",
    ),
    GroundingCase(
        "sup-earth-sun",
        "The Earth orbits the Sun.",
        "The Earth completes one heliocentric orbit around the Sun roughly every 365.25 days.",
        "supported",
    ),
    GroundingCase(
        "sup-photosynthesis",
        "Plants produce oxygen during photosynthesis.",
        "In photosynthesis, plants convert carbon dioxide and water into glucose and release oxygen as a byproduct.",
        "supported",
    ),
    GroundingCase(
        "sup-paris-capital",
        "Paris is the capital of France.",
        "France's capital and most populous city is Paris, seat of its national government.",
        "supported",
    ),
    GroundingCase(
        "sup-prime-seven",
        "Seven is a prime number.",
        "A prime has exactly two positive divisors, 1 and itself; 7 is divisible only by 1 and 7.",
        "supported",
    ),
    GroundingCase(
        "sup-ww2-end",
        "World War II ended in 1945.",
        "The Second World War concluded in 1945 with the surrender of Germany in May and Japan in September.",
        "supported",
    ),
    GroundingCase(
        "sup-speed-light",
        "Light travels faster than sound.",
        "Light moves at about 300,000 km/s in a vacuum, vastly faster than sound's ~343 m/s in air.",
        "supported",
    ),
    GroundingCase(
        "sup-http-stateless",
        "HTTP is a stateless protocol.",
        "HTTP treats each request independently and retains no client state between requests by itself.",
        "supported",
    ),
    GroundingCase(
        "sup-mercury-planet",
        "Mercury is the closest planet to the Sun.",
        "Of the eight planets, Mercury has the smallest orbit and is nearest to the Sun.",
        "supported",
    ),
    GroundingCase(
        "sup-mammal-warm",
        "Mammals are warm-blooded.",
        "Mammals are endothermic: they regulate and maintain a stable internal body temperature metabolically.",
        "supported",
    ),
    # --- contradicted: evidence refutes the claim ---
    GroundingCase(
        "con-water-freeze",
        "Water freezes at 50 degrees Celsius.",
        "Pure water freezes at 0 degrees Celsius at standard atmospheric pressure.",
        "contradicted",
    ),
    GroundingCase(
        "con-sun-orbits-earth",
        "The Sun orbits the Earth.",
        "The Earth and the other planets orbit the Sun, which sits at the center of the solar system.",
        "contradicted",
    ),
    GroundingCase(
        "con-berlin-france",
        "Berlin is the capital of France.",
        "Berlin is the capital of Germany; the capital of France is Paris.",
        "contradicted",
    ),
    GroundingCase(
        "con-eight-prime",
        "Eight is a prime number.",
        "Eight equals 2 times 2 times 2, so it has divisors 1, 2, 4, and 8 and is not prime.",
        "contradicted",
    ),
    GroundingCase(
        "con-sound-faster",
        "Sound travels faster than light.",
        "Light in a vacuum travels at about 300,000 km/s, far faster than sound at roughly 343 m/s in air.",
        "contradicted",
    ),
    GroundingCase(
        "con-ww2-1918",
        "World War II ended in 1918.",
        "The First World War ended in 1918; the Second World War ended in 1945.",
        "contradicted",
    ),
    GroundingCase(
        "con-spiders-insects",
        "Spiders are insects.",
        "Spiders are arachnids with eight legs and two body segments; insects have six legs and three body segments.",
        "contradicted",
    ),
    GroundingCase(
        "con-everest-shortest",
        "Mount Everest is the shortest mountain on Earth.",
        "Mount Everest is Earth's highest mountain above sea level, at about 8,849 meters.",
        "contradicted",
    ),
    GroundingCase(
        "con-oxygen-metal",
        "Oxygen is a metal.",
        "Oxygen is a non-metallic chemical element, a gas at room temperature in its common diatomic form.",
        "contradicted",
    ),
    GroundingCase(
        "con-python-compiled",
        "Python is a statically typed, compiled language.",
        "Python is a dynamically typed language that is interpreted (or bytecode-compiled at runtime), not statically typed.",
        "contradicted",
    ),
    # --- unrelated: evidence does not address the claim ---
    GroundingCase(
        "unr-cats-mars",
        "Cats are popular household pets.",
        "Mars is the fourth planet from the Sun and has two small moons, Phobos and Deimos.",
        "unrelated",
    ),
    GroundingCase(
        "unr-coffee-gravity",
        "Coffee contains caffeine.",
        "Gravity is the attractive force between masses; on Earth it accelerates objects at about 9.8 m/s squared.",
        "unrelated",
    ),
    GroundingCase(
        "unr-guitar-tax",
        "A guitar typically has six strings.",
        "Progressive income tax applies higher marginal rates to higher income brackets.",
        "unrelated",
    ),
    GroundingCase(
        "unr-ocean-chess",
        "The Pacific is the largest ocean.",
        "Chess is a two-player strategy board game played on an eight-by-eight grid of sixty-four squares.",
        "unrelated",
    ),
    GroundingCase(
        "unr-bread-comet",
        "Bread is made from flour.",
        "A comet is an icy small body that releases gas and dust, forming a tail when near the Sun.",
        "unrelated",
    ),
    GroundingCase(
        "unr-piano-volcano",
        "A standard piano has 88 keys.",
        "A volcano is a rupture in a planet's crust that allows lava, ash, and gases to escape.",
        "unrelated",
    ),
    GroundingCase(
        "unr-shark-algebra",
        "Sharks are fish.",
        "Algebra uses symbols and letters to represent numbers and quantities in equations and formulas.",
        "unrelated",
    ),
    GroundingCase(
        "unr-rain-currency",
        "Rain forms from condensed water vapor.",
        "A currency's exchange rate is the price at which it can be exchanged for another currency.",
        "unrelated",
    ),
    GroundingCase(
        "unr-honey-transistor",
        "Bees produce honey.",
        "A transistor is a semiconductor device used to amplify or switch electronic signals.",
        "unrelated",
    ),
    GroundingCase(
        "unr-desert-opera",
        "Deserts receive little rainfall.",
        "Opera is a staged dramatic work in which singing carries the story, usually with an orchestra.",
        "unrelated",
    ),
)


def load_grounding_cases(payload: Any) -> list[GroundingCase]:
    """Parse a JSON array of ``{case_id, claim, evidence, label}`` objects."""
    if not isinstance(payload, list):
        raise ValueError("grounding cases must be a JSON array of objects")
    cases: list[GroundingCase] = []
    for i, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise ValueError(f"case #{i} must be an object")
        cases.append(
            GroundingCase(
                case_id=str(raw.get("case_id") or f"case-{i}"),
                claim=str(raw.get("claim", "")),
                evidence=str(raw.get("evidence", "")),
                label=str(raw.get("label", "")),
            )
        )
    if not cases:
        raise ValueError("no grounding cases supplied")
    return cases


def _verdict_supported(verdict: GroundingVerdict) -> bool | None:
    """Extract the tri-state support from a CheckVerdict-shaped result."""
    return getattr(verdict, "supported", None)


def _classify(label: str, supported: bool | None) -> str:
    """Deterministically classify one (label, verdict) pair.

    A correct checker returns supported=True only when the evidence entails the
    claim. Anything else on a "supported" case is a miss; a True on a
    "contradicted"/"unrelated" case is a false support (the dangerous error).
    """
    if supported is None:
        return "abstained"
    if label == "supported":
        return "true_support" if supported else "missed_support"
    # label is contradicted or unrelated: the correct verdict is "not supported".
    return "false_support" if supported else "correct_reject"


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def build_grounding_correctness_report(
    cases: Sequence[GroundingCase],
    verdicts: Sequence[GroundingVerdict],
) -> dict[str, Any]:
    """Score checker verdicts against ground-truth labels. Deterministic, pure.

    ``verdicts[i]`` is the checker's CheckVerdict-shaped result for ``cases[i]``.
    Returns the ``deepr-grounding-correctness-v1`` report: support precision /
    recall, false-support and abstention rates, per-label accuracy, and the
    verdict-vs-label confusion matrix.
    """
    if len(cases) != len(verdicts):
        raise ValueError("cases and verdicts must be the same length")

    categories: Counter[str] = Counter()
    per_label: dict[str, Counter[str]] = {label: Counter() for label in _LABELS}
    confusion: Counter[tuple[str, str]] = Counter()
    per_case: list[dict[str, Any]] = []

    for case, verdict in zip(cases, verdicts, strict=True):
        supported = _verdict_supported(verdict)
        category = _classify(case.label, supported)
        categories[category] += 1
        per_label[case.label][category] += 1
        verdict_key = (
            "supported" if supported is True else "not_supported" if supported is False else "could_not_verify"
        )
        confusion[(case.label, verdict_key)] += 1
        per_case.append(
            {
                "case_id": case.case_id,
                "label": case.label,
                "verdict": verdict_key,
                "category": category,
                "correct": category in ("true_support", "correct_reject"),
            }
        )

    total = len(cases)
    supported_verdicts = categories["true_support"] + categories["false_support"]
    entailed_cases = sum(1 for c in cases if c.label == "supported")
    non_entailed_cases = total - entailed_cases
    correct = categories["true_support"] + categories["correct_reject"]

    label_accuracy = {
        label: _rate(
            counts["true_support"] + counts["correct_reject"],
            sum(counts.values()),
        )
        for label, counts in per_label.items()
    }

    return {
        "schema_version": GROUNDING_CORRECTNESS_SCHEMA_VERSION,
        "kind": GROUNDING_CORRECTNESS_KIND,
        "contract": {
            "read_only": True,
            "measures": "entailment-verdict correctness on curated ground-truth cases",
            "caveat": (
                "Agreement on a bounded curated set is not proof of world-truth. "
                "Labels are human-curated entailment judgments; the checker (model) "
                "owns the verdict, this scoring is deterministic."
            ),
        },
        "case_count": total,
        "label_counts": {label: sum(per_label[label].values()) for label in _LABELS},
        # Headline: when the checker stamps SUPPORTED, how often is it genuinely
        # entailed. This is the "trust a verified belief" number.
        "support_precision": _rate(categories["true_support"], supported_verdicts),
        # Of genuinely-entailed cases, how many did it confirm.
        "support_recall": _rate(categories["true_support"], entailed_cases),
        # The dangerous error: stamping SUPPORTED for contradicted/unrelated evidence.
        "false_support_rate": _rate(categories["false_support"], non_entailed_cases),
        # Could-not-verify responses (the checker never invents a verdict).
        "abstention_rate": _rate(categories["abstained"], total),
        "overall_accuracy": _rate(correct, total),
        "category_counts": dict(categories),
        "label_accuracy": label_accuracy,
        "confusion_matrix": {f"{label}->{verdict}": count for (label, verdict), count in sorted(confusion.items())},
        "cases": per_case,
    }


async def run_grounding_correctness_eval(
    cases: Sequence[GroundingCase],
    checker: GroundingChecker,
) -> dict[str, Any]:
    """Run ``checker`` over ``cases`` and score the verdicts. The checker owns meaning."""
    verdicts = [await checker(case.claim, case.evidence) for case in cases]
    return build_grounding_correctness_report(cases, verdicts)


def write_grounding_correctness_report(report: Mapping[str, Any], *, output_dir: Path | None = None) -> Path:
    """Write the report as a JSON artifact under the configured benchmarks directory."""
    import json
    from datetime import UTC, datetime

    from deepr.config import runtime_data_path

    root = output_dir or runtime_data_path("benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"grounding_correctness_{timestamp}.json"
    path.write_text(json.dumps(dict(report), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


__all__ = [
    "DEFAULT_GROUNDING_CASES",
    "GROUNDING_CORRECTNESS_KIND",
    "GROUNDING_CORRECTNESS_SCHEMA_VERSION",
    "GroundingCase",
    "build_grounding_correctness_report",
    "load_grounding_cases",
    "run_grounding_correctness_eval",
    "write_grounding_correctness_report",
]
