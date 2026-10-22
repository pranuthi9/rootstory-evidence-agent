from copy import deepcopy

import pytest

from evidence_agent.quotas import (
    DAY_MS,
    HOUR_MS,
    MAX_OVERRIDE_MS,
    QuotaExceeded,
    person_research_reservation,
)

NOW = 1_800_000_000_000


def usage(hour=0, day=0, hour_start=NOW, day_start=NOW):
    return {
        "userId": "owner",
        "actions": {
            "personResearch": {
                "hour": {"windowStart": hour_start, "count": hour},
                "day": {"windowStart": day_start, "count": day},
            },
            "familyStory": {"hour": {"windowStart": NOW, "count": 3}},
        },
    }


def override(hourly=10, daily=20, expires_at=NOW + HOUR_MS):
    return {
        "userId": "owner",
        "actions": {"personResearch": {"hourly": hourly, "daily": daily, "expiresAt": expires_at}},
    }


def test_first_reservation_anchors_both_windows_without_mutating_inputs():
    original = usage(hour=2, day=3)
    previous = deepcopy(original)
    assert person_research_reservation("owner", None, None, NOW) == {
        "hour": {"windowStart": NOW, "count": 1},
        "day": {"windowStart": NOW, "count": 1},
    }
    result = person_research_reservation("owner", original, None, NOW + 1000)
    assert result["hour"] == {"windowStart": NOW, "count": 3}
    assert result["day"] == {"windowStart": NOW, "count": 4}
    assert original == previous


def test_hour_and_day_reset_at_exact_duration_boundary():
    original = usage(hour=5, day=10, hour_start=NOW - HOUR_MS, day_start=NOW - DAY_MS)
    result = person_research_reservation("owner", original, None, NOW)
    assert result["hour"] == {"windowStart": NOW, "count": 1}
    assert result["day"] == {"windowStart": NOW, "count": 1}


def test_hour_reset_does_not_reset_daily_allowance():
    with pytest.raises(QuotaExceeded) as raised:
        person_research_reservation(
            "owner", usage(hour=5, day=10, hour_start=NOW - HOUR_MS), None, NOW
        )
    assert raised.value.retry_after_seconds == DAY_MS // 1000
    assert "daily" in str(raised.value)


def test_retry_after_uses_latest_exhausted_reset_and_rounds_up():
    with pytest.raises(QuotaExceeded) as raised:
        person_research_reservation("owner", usage(hour=5, day=10), None, NOW + 1)
    assert raised.value.retry_after_seconds == DAY_MS // 1000


def test_higher_override_preserves_existing_usage_and_clear_restores_defaults():
    previous = usage(hour=5, day=5)
    result = person_research_reservation("owner", previous, override(), NOW)
    assert result["hour"]["count"] == result["day"]["count"] == 6
    previous["actions"]["personResearch"] = result
    with pytest.raises(QuotaExceeded):
        person_research_reservation("owner", previous, None, NOW)


def test_expired_override_is_ignored_even_if_old_limits_are_invalid():
    expired = override(hourly="old", expires_at=NOW)
    with pytest.raises(QuotaExceeded) as raised:
        person_research_reservation("owner", usage(hour=5, day=5), expired, NOW)
    assert raised.value.retry_after_seconds == HOUR_MS // 1000


def test_zero_override_blocks_until_its_expiry():
    with pytest.raises(QuotaExceeded) as raised:
        person_research_reservation("owner", None, override(0, 10, NOW + 2 * HOUR_MS), NOW)
    assert raised.value.retry_after_seconds == 2 * HOUR_MS // 1000


def test_override_expiry_can_allow_policy_reassessment_before_window_reset():
    with pytest.raises(QuotaExceeded) as raised:
        person_research_reservation("owner", usage(hour=2), override(2, 10, NOW + 10_001), NOW)
    assert raised.value.retry_after_seconds == 11


def test_expiring_higher_override_cannot_retry_before_lower_default_daily_limit_resets():
    with pytest.raises(QuotaExceeded) as raised:
        person_research_reservation(
            "owner", usage(hour=8, day=11), override(8, 12, NOW + 10_001), NOW
        )
    assert raised.value.retry_after_seconds == DAY_MS // 1000
    assert "8 per hour" in str(raised.value)


def test_zero_override_expiry_still_respects_previously_consumed_default_capacity():
    with pytest.raises(QuotaExceeded) as raised:
        person_research_reservation(
            "owner", usage(hour=5, day=10), override(0, 10, NOW + 10_001), NOW
        )
    assert raised.value.retry_after_seconds == DAY_MS // 1000


def test_integer_valued_firestore_numbers_match_javascript_number_semantics():
    previous = usage(hour=4.0, day=5.0)
    configured = override(hourly=8.0, daily=12.0)
    result = person_research_reservation("owner", previous, configured, NOW)
    assert result["hour"]["count"] == 5
    assert type(result["hour"]["count"]) is int


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("hourly", True),
        ("hourly", -1),
        ("hourly", 1001),
        ("hourly", 1.5),
        ("daily", 2),
        ("expiresAt", NOW + MAX_OVERRIDE_MS + 1),
        ("expiresAt", float("inf")),
    ],
)
def test_malformed_active_overrides_fail_closed(field, invalid):
    configured = override()
    configured["actions"]["personResearch"][field] = invalid
    with pytest.raises(ValueError):
        person_research_reservation("owner", None, configured, NOW)


@pytest.mark.parametrize(
    "window",
    [
        "invalid",
        {"windowStart": NOW, "count": -1},
        {"windowStart": NOW, "count": True},
        {"windowStart": float("nan"), "count": 0},
        {"windowStart": -1, "count": 0},
        {"windowStart": NOW},
    ],
)
def test_malformed_usage_windows_fail_closed(window):
    previous = usage()
    previous["actions"]["personResearch"]["hour"] = window
    with pytest.raises(ValueError):
        person_research_reservation("owner", previous, None, NOW)


@pytest.mark.parametrize("document", ["usage", "override"])
def test_persisted_document_identity_must_match_authenticated_user(document):
    previous, configured = usage(), override()
    (previous if document == "usage" else configured)["userId"] = "someone-else"
    with pytest.raises(ValueError):
        person_research_reservation("owner", previous, configured, NOW)
