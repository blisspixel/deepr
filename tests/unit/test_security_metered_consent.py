"""Exact acknowledgement tests for the shared metered API boundary."""

import pytest

from deepr.security.metered_consent import METERED_API_CONSENT_ERROR, metered_api_consent_error


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"allow_metered_api": True},
        {"confirm_metered_cost": True},
        {"allow_metered_api": 1, "confirm_metered_cost": True},
        {"allow_metered_api": True, "confirm_metered_cost": "true"},
    ],
)
def test_metered_api_consent_requires_two_exact_json_booleans(data):
    assert metered_api_consent_error(data) == METERED_API_CONSENT_ERROR


def test_metered_api_consent_accepts_both_exact_acknowledgements():
    assert metered_api_consent_error({"allow_metered_api": True, "confirm_metered_cost": True}) is None
