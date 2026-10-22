"""Shared personResearch policy used by both the host API and Evidence Agent."""

from math import ceil, isfinite

HOUR_MS = 60 * 60 * 1000
DAY_MS = 24 * HOUR_MS
MAX_OVERRIDE_MS = 30 * DAY_MS


class QuotaExceeded(Exception):
    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, retry_after_seconds)
        self.code = "ai_quota_exceeded"


def _finite_number(value) -> bool:
    return type(value) in {int, float} and isfinite(value)


def _integer(value) -> bool:
    return _finite_number(value) and value == int(value)


def current_window(value, duration: float, now: float) -> dict:
    if value is None:
        return {"windowStart": now, "count": 0}
    if (
        not isinstance(value, dict)
        or not _finite_number(value.get("windowStart"))
        or value["windowStart"] < 0
        or not _integer(value.get("count"))
        or value["count"] < 0
    ):
        raise ValueError("Invalid persisted AI usage window")
    if now - value["windowStart"] >= duration:
        return {"windowStart": now, "count": 0}
    return {"windowStart": value["windowStart"], "count": int(value["count"])}


def _actions(document: dict | None, user_id: str) -> dict:
    if document is None:
        return {}
    if not isinstance(document, dict) or document.get("userId") != user_id:
        raise ValueError("AI quota document identity mismatch")
    actions = document.get("actions", {})
    if not isinstance(actions, dict):
        raise TypeError("Invalid persisted AI action data")
    return actions


def person_research_reservation(
    user_id: str, usage: dict | None, overrides: dict | None, now_ms: int
) -> dict:
    actions = _actions(usage, user_id)
    action = actions.get("personResearch")
    if action is None:
        action = {}
    if not isinstance(action, dict):
        raise TypeError("Invalid persisted person research usage")
    hour = current_window(action.get("hour"), HOUR_MS, now_ms)
    day = current_window(action.get("day"), DAY_MS, now_ms)

    hourly, daily = 5, 10
    expires_at = None
    override = _actions(overrides, user_id).get("personResearch")
    if override is not None:
        if not isinstance(override, dict) or not _finite_number(override.get("expiresAt")):
            raise ValueError("Invalid person research override")
        if override["expiresAt"] > now_ms:
            hourly, daily = override.get("hourly"), override.get("daily")
            if (
                not _integer(hourly)
                or not _integer(daily)
                or not 0 <= hourly <= daily <= 1000
                or override["expiresAt"] > now_ms + MAX_OVERRIDE_MS
            ):
                raise ValueError("Invalid active person research override")
            hourly, daily = int(hourly), int(daily)
            expires_at = override["expiresAt"]

    exhausted = []
    if hour["count"] >= hourly:
        exhausted.append(hour["windowStart"] + HOUR_MS)
    if day["count"] >= daily:
        exhausted.append(day["windowStart"] + DAY_MS)
    if exhausted:
        retry_at = max(exhausted)
        paused = hourly == 0 or daily == 0
        if expires_at is not None and (paused or expires_at < retry_at):
            hour_reset, day_reset = hour["windowStart"] + HOUR_MS, day["windowStart"] + DAY_MS
            hourly_at_expiry = 0 if expires_at >= hour_reset else hour["count"]
            daily_at_expiry = 0 if expires_at >= day_reset else day["count"]
            retry_at = max(
                expires_at,
                hour_reset if hourly_at_expiry >= 5 else expires_at,
                day_reset if daily_at_expiry >= 10 else expires_at,
            )
        period = "daily" if day["count"] >= daily else "hourly"
        message = (
            "Person research is temporarily paused for your account. Please try again later."
            if paused
            else (
                f"You have reached the {period} person research limit "
                f"({daily if period == 'daily' else hourly} per "
                f"{'day' if period == 'daily' else 'hour'}). Please try again later."
            )
        )
        raise QuotaExceeded(
            message,
            ceil((retry_at - now_ms) / 1000),
        )
    return {
        "hour": {**hour, "count": hour["count"] + 1},
        "day": {**day, "count": day["count"] + 1},
    }
