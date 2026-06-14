"""Tests for the atomicity monitor (telemetry, never a gate).

These pin the two hard contracts from atomicity.py: the rate is a lexical
proxy (high-recall, not a verdict) and it is strictly non-gating - it can never
change an absorb outcome. The non-gating proof for the absorb path itself lives
in test_report_absorber.py; here we prove the measurement function is pure.
"""

from deepr.experts.atomicity import AtomicityReport, atomicity_report, looks_compound


class TestLooksCompound:
    def test_single_assertion_is_not_compound(self):
        assert looks_compound("The system uses SQLite for local storage") is False

    def test_conjunction_flags_compound(self):
        assert looks_compound("The system uses SQLite and Postgres for storage") is True

    def test_semicolon_flags_compound(self):
        assert looks_compound("Costs are tracked; budgets are enforced") is True

    def test_whereas_flags_compound(self):
        assert looks_compound("Gemini is cheap whereas o3 is expensive") is True

    def test_empty_is_not_compound(self):
        assert looks_compound("") is False

    def test_marker_needs_word_boundary(self):
        # "brand" contains "and" but is one assertion - boundaries prevent the
        # naive substring false positive.
        assert looks_compound("The brand is well known") is False


class TestAtomicityReport:
    def test_empty_batch_is_vacuously_atomic(self):
        report = atomicity_report([])
        assert report.total == 0
        assert report.rate == 1.0
        assert report.compound_examples == ()

    def test_all_atomic(self):
        report = atomicity_report(["A is true", "B is false", "C holds"])
        assert report.total == 3
        assert report.atomic == 3
        assert report.compound == 0
        assert report.rate == 1.0

    def test_mixed_rate(self):
        report = atomicity_report(
            [
                "Python is fast",  # atomic
                "Python is fast and Java is slow",  # compound
                "Costs tracked; budgets enforced",  # compound
                "Rust is memory safe",  # atomic
            ]
        )
        assert report.total == 4
        assert report.compound == 2
        assert report.atomic == 2
        assert report.rate == 0.5

    def test_examples_capped(self):
        statements = [f"X{i} holds and Y{i} holds" for i in range(10)]
        report = atomicity_report(statements, max_examples=3)
        assert report.compound == 10
        assert len(report.compound_examples) == 3

    def test_to_dict_stamps_proxy_and_non_gating_contract(self):
        d = atomicity_report(["A and B"]).to_dict()
        assert d["signal"] == "lexical_proxy"
        assert d["gating"] is False
        assert d["rate"] == 0.0

    def test_report_is_frozen(self):
        report = atomicity_report(["A is true"])
        assert isinstance(report, AtomicityReport)
        try:
            report.total = 99  # type: ignore[misc]
        except Exception as exc:
            assert "cannot assign" in str(exc).lower() or "frozen" in str(exc).lower()
        else:  # pragma: no cover - frozen dataclass must reject mutation
            raise AssertionError("AtomicityReport must be immutable")
