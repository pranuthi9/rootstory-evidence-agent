from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil
from threading import Lock

from google.cloud import firestore

from .models import AuditRun, TreeSnapshot
from .quotas import HOUR_MS, QuotaExceeded, current_window, person_research_reservation


class EvidenceStore(ABC):
    @abstractmethod
    def save_run(self, run: AuditRun) -> None: ...

    @abstractmethod
    def get_run(self, run_id: str) -> AuditRun | None: ...

    @abstractmethod
    def get_latest_run(self, tree_id: str, owner_id: str) -> AuditRun | None: ...

    @abstractmethod
    def save_tree(self, tree: TreeSnapshot) -> None: ...

    @abstractmethod
    def get_tree(self, tree_id: str) -> TreeSnapshot | None: ...


class MemoryEvidenceStore(EvidenceStore):
    def __init__(self) -> None:
        self._runs: dict[str, AuditRun] = {}
        self._trees: dict[str, TreeSnapshot] = {}
        self._lock = Lock()

    def save_run(self, run: AuditRun) -> None:
        with self._lock:
            self._runs[run.id] = deepcopy(run)

    def get_run(self, run_id: str) -> AuditRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            return deepcopy(run) if run else None

    def get_latest_run(self, tree_id: str, owner_id: str) -> AuditRun | None:
        with self._lock:
            matches = [
                run
                for run in self._runs.values()
                if run.tree_id == tree_id and run.owner_id == owner_id
            ]
            latest = max(matches, key=lambda run: run.created_at, default=None)
            return deepcopy(latest) if latest else None

    def save_tree(self, tree: TreeSnapshot) -> None:
        with self._lock:
            self._trees[tree.id] = deepcopy(tree)

    def get_tree(self, tree_id: str) -> TreeSnapshot | None:
        with self._lock:
            tree = self._trees.get(tree_id)
            return deepcopy(tree) if tree else None


class FirestoreEvidenceStore(EvidenceStore):
    """Durable run and snapshot store shared by independent Cloud Run requests."""

    def __init__(self, project: str | None = None) -> None:
        self._db = firestore.Client(project=project)
        self._runs = self._db.collection("evidenceAuditRuns")
        self._trees = self._db.collection("evidenceTreeSnapshots")

    def reserve_audit_start(self, user_id: str, tree_id: str) -> bool:
        """Verify actual ownership and reserve bounded work across all instances."""
        owner_ref = self._db.collection("familyTrees").document(tree_id)
        user_key = sha256(user_id.encode()).hexdigest()
        user_usage = self._db.collection("aiUsage").document(user_key)
        user_override = self._db.collection("aiQuotaOverrides").document(user_key)
        global_limit = self._db.collection("rateLimits").document("global_evidenceAuditStart")

        @firestore.transactional
        def reserve(transaction):
            tree = owner_ref.get(transaction=transaction)
            if not tree.exists or tree.to_dict().get("userId") != user_id:
                raise PermissionError("Not the stored tree owner")
            usage = user_usage.get(transaction=transaction)
            override = user_override.get(transaction=transaction)
            global_snapshot = global_limit.get(transaction=transaction)
            now_ms = int(datetime.now(UTC).timestamp() * 1000)

            # Preserve the existing global counter's seconds-based schema.
            global_window = current_window(
                global_snapshot.to_dict() if global_snapshot.exists else None,
                HOUR_MS / 1000,
                now_ms / 1000,
            )
            blocked = None
            try:
                next_usage = person_research_reservation(
                    user_id,
                    usage.to_dict() if usage.exists else None,
                    override.to_dict() if override.exists else None,
                    now_ms,
                )
            except QuotaExceeded as exc:
                blocked = exc

            if global_window["count"] >= 100:
                retry = ceil(global_window["windowStart"] + 3600 - now_ms / 1000)
                blocked = QuotaExceeded(
                    "Research is busy. Please try again later.",
                    max(retry, blocked.retry_after_seconds if blocked else 1),
                )
            if blocked:
                raise blocked

            # All ownership/policy/global checks finish before either write.
            # Merging keeps usage from the host API's other AI actions intact.
            transaction.set(
                user_usage,
                {"userId": user_id, "actions": {"personResearch": next_usage}},
                merge=True,
            )
            transaction.set(global_limit, {**global_window, "count": global_window["count"] + 1})
            return True

        return reserve(self._db.transaction())

    def save_run(self, run: AuditRun) -> None:
        self._runs.document(run.id).set(run.model_dump(mode="json"))

    def get_run(self, run_id: str) -> AuditRun | None:
        snapshot = self._runs.document(run_id).get()
        return AuditRun.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def get_latest_run(self, tree_id: str, owner_id: str) -> AuditRun | None:
        snapshots = self._runs.where("tree_id", "==", tree_id).stream()
        matches = [
            AuditRun.model_validate(snapshot.to_dict())
            for snapshot in snapshots
            if snapshot.to_dict().get("owner_id") == owner_id
        ]
        return max(matches, key=lambda run: run.created_at, default=None)

    def save_tree(self, tree: TreeSnapshot) -> None:
        self._trees.document(tree.id).set(tree.model_dump(mode="json"))

    def get_tree(self, tree_id: str) -> TreeSnapshot | None:
        snapshot = self._trees.document(tree_id).get()
        return TreeSnapshot.model_validate(snapshot.to_dict()) if snapshot.exists else None
