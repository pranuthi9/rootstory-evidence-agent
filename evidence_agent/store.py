from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from threading import Lock

from google.cloud import firestore

from .models import AuditRun, TreeSnapshot


class EvidenceStore(ABC):
    @abstractmethod
    def save_run(self, run: AuditRun) -> None: ...

    @abstractmethod
    def get_run(self, run_id: str) -> AuditRun | None: ...

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

    def save_run(self, run: AuditRun) -> None:
        self._runs.document(run.id).set(run.model_dump(mode="json"))

    def get_run(self, run_id: str) -> AuditRun | None:
        snapshot = self._runs.document(run_id).get()
        return AuditRun.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save_tree(self, tree: TreeSnapshot) -> None:
        self._trees.document(tree.id).set(tree.model_dump(mode="json"))

    def get_tree(self, tree_id: str) -> TreeSnapshot | None:
        snapshot = self._trees.document(tree_id).get()
        return TreeSnapshot.model_validate(snapshot.to_dict()) if snapshot.exists else None
