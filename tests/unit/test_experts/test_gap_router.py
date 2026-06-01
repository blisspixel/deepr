"""Tests for deepr.experts.gap_router.GapRouter."""

from __future__ import annotations

import pytest

from deepr.core.contracts import Gap
from deepr.experts.gap_router import DISTILLR, PRIMR, RECON, RESEARCH, GapRouter


def _gap(topic: str, *, cost: float = 0.0, ev: float = 1.0, priority: int = 3, questions=None) -> Gap:
    return Gap.create(topic=topic, estimated_cost=cost, ev_cost_ratio=ev, priority=priority, questions=questions or [])


_ALL_AVAILABLE = {"recon": True, "distillr": True, "primr": True}


class TestClassify:
    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("DMARC and email security posture of acme.com", RECON),
            ("Latest academic papers on diffusion models", DISTILLR),
            ("Company hiring signals and competitive positioning", PRIMR),
            ("General overview of robotics", RESEARCH),
        ],
    )
    def test_classify_picks_specialist(self, topic, expected):
        instrument, _matched = GapRouter.classify(topic)
        assert instrument == expected

    def test_no_signal_defaults_to_research(self):
        instrument, matched = GapRouter.classify("something entirely generic")
        assert instrument == RESEARCH
        assert matched == []

    def test_questions_contribute_signal(self):
        instrument, matched = GapRouter.classify("Open topic", questions=["What is their DNS and DMARC setup?"])
        assert instrument == RECON
        assert matched


class TestRouting:
    def test_routes_each_gap_to_specialist(self):
        router = GapRouter(available=_ALL_AVAILABLE)
        routes = router.route(
            [
                _gap("Company hiring and strategy", ev=2.0),
                _gap("Academic literature on LLMs", ev=1.5),
                _gap("Email security / DMARC posture", ev=1.0),
            ]
        )
        # Sorted by ev_cost_ratio desc.
        assert [r.instrument for r in routes] == [PRIMR, DISTILLR, RECON]
        assert all(r.available for r in routes)

    def test_unavailable_specialist_falls_back_to_research(self):
        router = GapRouter(available={"recon": False, "distillr": False, "primr": False})
        route = router.route_gap(_gap("Academic papers on transformers"))
        assert route.instrument == RESEARCH
        assert route.available is True
        assert "not installed" in route.rationale
        assert "pip install distillr" in route.rationale

    def test_research_route_uses_gap_cost(self):
        router = GapRouter(available=_ALL_AVAILABLE)
        route = router.route_gap(_gap("Generic topic", cost=0.75))
        assert route.instrument == RESEARCH
        assert route.estimated_cost == 0.75
        assert "deepr research" in route.suggestion

    def test_specialist_default_cost_when_gap_has_none(self):
        router = GapRouter(available=_ALL_AVAILABLE)
        route = router.route_gap(_gap("primr company deep-dive on competitors", cost=0.0))
        assert route.instrument == PRIMR
        assert route.estimated_cost == 5.0  # primr default

    def test_recon_is_free(self):
        router = GapRouter(available=_ALL_AVAILABLE)
        route = router.route_gap(_gap("tenant and saas fingerprint", cost=0.0))
        assert route.instrument == RECON
        assert route.estimated_cost == 0.0

    def test_to_dict_shape(self):
        router = GapRouter(available=_ALL_AVAILABLE)
        d = router.route_gap(_gap("hiring signals", ev=1.2, priority=4)).to_dict()
        assert set(d) >= {"topic", "instrument", "available", "estimated_cost", "rationale", "suggestion"}
        assert d["priority"] == 4

    def test_research_always_available_even_if_passed_false(self):
        router = GapRouter(available={"recon": False, "distillr": False, "primr": False})
        assert router.available[RESEARCH] is True
