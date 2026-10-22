"""Durable quota integration checks; explicitly require an isolated Firestore emulator."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest
from google.api_core.exceptions import Aborted

from evidence_agent.quotas import DAY_MS, HOUR_MS, QuotaExceeded
from evidence_agent.store import FirestoreEvidenceStore

pytestmark = pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"), reason="Requires a local Firestore emulator"
)


@pytest.fixture
def store():
    project = os.environ.get("GCLOUD_PROJECT", "demo-rootstory-evidence-abuse-tests")
    host = os.environ["FIRESTORE_EMULATOR_HOST"].split(":")[0]
    assert project.startswith("demo-")
    assert host in {"localhost", "127.0.0.1"}
    return FirestoreEvidenceStore(project=project)


def owner_tree(store, user_id):
    tree_id = f"quota-tree-{uuid4()}"
    store._db.collection("familyTrees").document(tree_id).set({"userId": user_id})
    return tree_id


def user_usage(store, user_id):
    return store._db.collection("aiUsage").document(sha256(user_id.encode()).hexdigest())


def user_override(store, user_id):
    return store._db.collection("aiQuotaOverrides").document(sha256(user_id.encode()).hexdigest())


def seed_usage(store, user_id, hour=0, day=0, hour_age=0, day_age=0):
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    user_usage(store, user_id).set(
        {
            "userId": user_id,
            "actions": {
                "personResearch": {
                    "hour": {"windowStart": now_ms - hour_age, "count": hour},
                    "day": {"windowStart": now_ms - day_age, "count": day},
                },
                "familyStory": {"hour": {"windowStart": now_ms, "count": 7}},
            },
        }
    )


def seed_override(store, user_id, hourly=10, daily=20, expires_in=HOUR_MS):
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    user_override(store, user_id).set(
        {
            "userId": user_id,
            "actions": {
                "personResearch": {
                    "hourly": hourly,
                    "daily": daily,
                    "expiresAt": now_ms + expires_in,
                    "reason": "Temporary approved research allowance",
                    "updatedBy": "quota-administrator",
                    "updatedAt": now_ms,
                }
            },
        }
    )


def global_count(store):
    return (
        store._db.collection("rateLimits")
        .document("global_evidenceAuditStart")
        .get()
        .to_dict()["count"]
    )


def reset_global(store, count=0, age=0):
    store._db.collection("rateLimits").document("global_evidenceAuditStart").set(
        {"count": count, "windowStart": datetime.now(UTC).timestamp() - age}
    )


def test_concurrent_instances_cannot_exceed_five_starts_even_under_contention(store):
    reset_global(store)
    user_id = f"concurrent-owner-{uuid4()}"
    tree_id = owner_tree(store, user_id)

    def reserve(_):
        independent_store = FirestoreEvidenceStore(project=store._db.project)
        try:
            return independent_store.reserve_audit_start(user_id, tree_id)
        except QuotaExceeded:
            return False
        except ValueError as exc:
            # Firestore retries may exhaust under contention. The API returns 503
            # before creating work; a failed reservation must never be counted.
            if isinstance(exc.__cause__, Aborted):
                return None
            raise

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(reserve, range(8)))
    reserved = results.count(True)
    assert 0 < reserved <= 5
    persisted = user_usage(store, user_id).get().to_dict()["actions"]["personResearch"]
    assert persisted["hour"]["count"] == persisted["day"]["count"] == reserved
    for _ in range(5 - reserved):
        assert store.reserve_audit_start(user_id, tree_id) is True
    with pytest.raises(QuotaExceeded):
        store.reserve_audit_start(user_id, tree_id)
    persisted = user_usage(store, user_id).get().to_dict()["actions"]["personResearch"]
    assert persisted["hour"]["count"] == persisted["day"]["count"] == 5
    assert global_count(store) == 5


def test_global_quota_blocks_new_accounts_without_consuming_user_allowance(store):
    reset_global(store, count=99)
    first_user, second_user = f"first-{uuid4()}", f"second-{uuid4()}"
    first_tree, second_tree = owner_tree(store, first_user), owner_tree(store, second_user)
    assert store.reserve_audit_start(first_user, first_tree) is True
    seed_override(store, second_user, hourly=1000, daily=1000)
    with pytest.raises(QuotaExceeded) as raised:
        store.reserve_audit_start(second_user, second_tree)
    assert 3590 <= raised.value.retry_after_seconds <= 3600
    assert not user_usage(store, second_user).get().exists
    assert global_count(store) == 100


def test_expired_windows_reset_the_user_and_global_allowances(store):
    reset_global(store, count=100, age=3601)
    user_id = f"expired-{uuid4()}"
    tree_id = owner_tree(store, user_id)
    seed_usage(store, user_id, hour=5, day=10, hour_age=HOUR_MS, day_age=DAY_MS)
    assert store.reserve_audit_start(user_id, tree_id) is True
    persisted = user_usage(store, user_id).get().to_dict()["actions"]["personResearch"]
    assert persisted["hour"]["count"] == persisted["day"]["count"] == 1
    assert global_count(store) == 1


def test_forged_snapshot_owner_cannot_reserve_or_overwrite_another_tree(store):
    reset_global(store)
    actual_owner, attacker = f"victim-{uuid4()}", f"attacker-{uuid4()}"
    tree_id = owner_tree(store, actual_owner)
    with pytest.raises(PermissionError):
        store.reserve_audit_start(attacker, tree_id)
    assert not user_usage(store, attacker).get().exists
    assert global_count(store) == 0
    assert store._db.collection("familyTrees").document(tree_id).get().to_dict() == {
        "userId": actual_owner
    }


def test_shared_host_usage_is_consumed_without_overwriting_other_actions(store):
    reset_global(store)
    user_id = f"shared-{uuid4()}"
    tree_id = owner_tree(store, user_id)
    seed_usage(store, user_id, hour=4, day=7)
    before = user_usage(store, user_id).get().to_dict()
    assert store.reserve_audit_start(user_id, tree_id) is True
    after = user_usage(store, user_id).get().to_dict()
    assert after["actions"]["familyStory"] == before["actions"]["familyStory"]
    assert after["actions"]["personResearch"]["hour"] == {
        **before["actions"]["personResearch"]["hour"],
        "count": 5,
    }
    assert after["actions"]["personResearch"]["day"]["count"] == 8
    with pytest.raises(QuotaExceeded):
        store.reserve_audit_start(user_id, tree_id)
    assert user_usage(store, user_id).get().to_dict() == after
    assert global_count(store) == 1


def test_daily_limit_does_not_consume_new_hour_or_global_allowance(store):
    reset_global(store, count=12)
    user_id = f"daily-{uuid4()}"
    tree_id = owner_tree(store, user_id)
    seed_usage(store, user_id, hour=5, day=10, hour_age=HOUR_MS, day_age=60_000)
    before = user_usage(store, user_id).get().to_dict()
    with pytest.raises(QuotaExceeded) as raised:
        store.reserve_audit_start(user_id, tree_id)
    assert 86_330 <= raised.value.retry_after_seconds <= 86_340
    assert "daily" in str(raised.value)
    assert user_usage(store, user_id).get().to_dict() == before
    assert global_count(store) == 12


def test_temporary_override_can_increase_limits_but_expiry_or_clear_preserves_usage(store):
    reset_global(store)
    user_id = f"override-{uuid4()}"
    tree_id = owner_tree(store, user_id)
    seed_usage(store, user_id, hour=5, day=5)
    with pytest.raises(QuotaExceeded):
        store.reserve_audit_start(user_id, tree_id)
    seed_override(store, user_id, hourly=8, daily=12)
    assert store.reserve_audit_start(user_id, tree_id) is True
    assert (
        user_usage(store, user_id).get().to_dict()["actions"]["personResearch"]["hour"]["count"]
        == 6
    )
    seed_override(store, user_id, hourly=8, daily=12, expires_in=-1)
    with pytest.raises(QuotaExceeded):
        store.reserve_audit_start(user_id, tree_id)
    seed_override(store, user_id, hourly=8, daily=12)
    assert store.reserve_audit_start(user_id, tree_id) is True
    user_override(store, user_id).delete()
    before = user_usage(store, user_id).get().to_dict()
    with pytest.raises(QuotaExceeded):
        store.reserve_audit_start(user_id, tree_id)
    assert user_usage(store, user_id).get().to_dict() == before
    assert before["actions"]["personResearch"]["hour"]["count"] == 7
    assert global_count(store) == 2


def test_invalid_override_or_usage_cannot_reserve_global_allowance(store):
    reset_global(store, count=3)
    user_id = f"invalid-{uuid4()}"
    tree_id = owner_tree(store, user_id)
    seed_override(store, user_id, hourly=1001, daily=1001)
    with pytest.raises(ValueError):
        store.reserve_audit_start(user_id, tree_id)
    assert not user_usage(store, user_id).get().exists
    assert global_count(store) == 3
    user_override(store, user_id).delete()
    seed_usage(store, user_id)
    user_usage(store, user_id).update({"userId": "wrong-owner"})
    with pytest.raises(ValueError):
        store.reserve_audit_start(user_id, tree_id)
    assert global_count(store) == 3
