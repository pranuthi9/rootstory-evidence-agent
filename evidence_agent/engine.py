from __future__ import annotations

from collections import Counter

from .agents import EvidenceResearcher
from .models import (
    AgentEvent,
    AuditMetrics,
    AuditRun,
    Finding,
    FindingKind,
    PatchOperation,
    Proposal,
    ResearchTask,
    RunStatus,
    TaskStatus,
    TreeSnapshot,
    utc_now,
)
from .store import EvidenceStore

CORE_FIELDS = ("name", "birthDate", "deathDate", "birthPlace")


class EvidenceEngine:
    def __init__(self, store: EvidenceStore, researcher: EvidenceResearcher) -> None:
        self.store = store
        self.researcher = researcher

    def start(self, tree: TreeSnapshot, auto_apply_safe: bool = False) -> AuditRun:
        run = AuditRun(tree_id=tree.id, owner_id=tree.owner_id, auto_apply_safe=auto_apply_safe)
        self.store.save_tree(tree)
        self._event(run, "system", "audit_started", "Evidence audit queued")
        self.store.save_run(run)
        return run

    def plan(self, run_id: str) -> AuditRun:
        run = self._require_run(run_id)
        if run.status != RunStatus.QUEUED:
            return run
        tree = self._require_tree(run.tree_id)
        run.status = RunStatus.AUDITING
        run.metrics_before = self._metrics(tree)
        run.findings = self._audit(tree)
        run.tasks = [
            ResearchTask(
                run_id=run.id,
                finding_id=finding.id,
                subject_id=finding.subject_id,
                objective=finding.description,
            )
            for finding in sorted(run.findings, key=lambda item: item.priority, reverse=True)
            if finding.kind in {FindingKind.MISSING_CITATION, FindingKind.MISSING_FACT}
        ]
        run.status = RunStatus.RESEARCHING if run.tasks else RunStatus.COMPLETED
        self._event(
            run,
            "planner",
            "plan_created",
            f"Found {len(run.findings)} evidence gaps and created {len(run.tasks)} tasks",
        )
        if not run.tasks:
            run.metrics_after = run.metrics_before
        self._save(run)
        return run

    def work_next(self, run_id: str) -> AuditRun:
        run = self._require_run(run_id)
        if run.status not in {RunStatus.RESEARCHING, RunStatus.VERIFYING}:
            return run
        # The queue is configured for one concurrent dispatch. Reclaiming a persisted
        # RUNNING task makes a Cloud Tasks retry resume work after a container crash.
        task = next((item for item in run.tasks if item.status == TaskStatus.RUNNING), None)
        task = task or next((item for item in run.tasks if item.status == TaskStatus.QUEUED), None)
        if task is None:
            return self._finish_verification(run)
        tree = self._require_tree(run.tree_id)
        person = next((item for item in tree.people if item.get("id") == task.subject_id), None)
        finding = next(item for item in run.findings if item.id == task.finding_id)
        if person is None:
            task.status = TaskStatus.FAILED
            task.error = "Subject no longer exists in the tree"
            self._event(run, "researcher", "task_failed", task.error, {"taskId": task.id})
            self._save(run)
            return run

        task.status = TaskStatus.RUNNING
        task.attempt_count += 1
        task.updated_at = utc_now()
        self._event(run, "researcher", "task_started", task.objective, {"taskId": task.id})
        self._save(run)
        try:
            task.claims = self.researcher.research(person, finding)
            task.status = TaskStatus.COMPLETED
            task.updated_at = utc_now()
            self._event(
                run,
                "researcher",
                "task_completed",
                f"Research task produced {len(task.claims)} candidate claims",
                {"taskId": task.id},
            )
        except Exception as exc:  # noqa: BLE001 - provider failures must become durable retry state
            task.status = TaskStatus.QUEUED if task.attempt_count < 3 else TaskStatus.FAILED
            task.error = str(exc)
            self._event(
                run,
                "system",
                "task_retry_scheduled" if task.status == TaskStatus.QUEUED else "task_failed",
                "Research provider failed; progress was preserved",
                {"taskId": task.id, "attempt": task.attempt_count},
            )
        self._save(run)
        if not any(item.status == TaskStatus.QUEUED for item in run.tasks):
            return self._finish_verification(run)
        return run

    def decide(self, run_id: str, proposal_id: str, decision: str) -> AuditRun:
        run = self._require_run(run_id)
        proposal = next((item for item in run.proposals if item.id == proposal_id), None)
        if proposal is None:
            raise KeyError("Proposal not found")
        if proposal.decision != "pending":
            return run
        proposal.decision = decision  # validated by request model
        self._event(
            run,
            "system",
            "proposal_decided",
            f"Proposal {decision}",
            {"proposalId": proposal.id},
        )
        self._save(run)
        return run

    def apply(self, run_id: str) -> AuditRun:
        run = self._require_run(run_id)
        tree = self._require_tree(run.tree_id)
        run.status = RunStatus.APPLYING
        for proposal in run.proposals:
            if proposal.decision != "approved":
                continue
            person = next(
                (item for item in tree.people if item.get("id") == proposal.subject_id), None
            )
            if not person:
                continue
            field = proposal.patch.path.removeprefix("/")
            if proposal.patch.operation in {"add", "replace"}:
                person[field] = proposal.patch.value
                proposal.decision = "applied"
                self._event(
                    run,
                    "repairer",
                    "patch_applied",
                    proposal.summary,
                    {"proposalId": proposal.id, "path": proposal.patch.path},
                )
        self.store.save_tree(tree)
        run.metrics_after = self._metrics(tree)
        pending = any(item.decision == "pending" for item in run.proposals)
        run.status = RunStatus.AWAITING_REVIEW if pending else RunStatus.COMPLETED
        if run.status == RunStatus.COMPLETED:
            self._event(run, "system", "audit_completed", "Evidence audit completed")
        self._save(run)
        return run

    def _finish_verification(self, run: AuditRun) -> AuditRun:
        run.status = RunStatus.VERIFYING
        findings = {item.id: item for item in run.findings}
        for task in run.tasks:
            finding = findings[task.finding_id]
            for claim in task.claims:
                if finding.field and claim.field != finding.field:
                    continue
                if not claim.sources or claim.confidence < 0.65:
                    continue
                current = finding.current_value
                operation = "add" if current in (None, "", []) else "replace"
                risk = (
                    "low"
                    if operation == "add" and finding.kind == FindingKind.MISSING_CITATION
                    else "medium"
                )
                proposal = Proposal(
                    run_id=run.id,
                    finding_id=finding.id,
                    subject_id=claim.subject_id,
                    summary=f"Add evidence for {claim.field}"
                    if operation == "add"
                    else f"Review change to {claim.field}",
                    patch=PatchOperation(
                        operation=operation,
                        path=f"/{claim.field}",
                        value=claim.value,
                        previous_value=current,
                    ),
                    sources=claim.sources,
                    confidence=claim.confidence,
                    risk=risk,
                    requires_approval=not (run.auto_apply_safe and risk == "low"),
                )
                if not proposal.requires_approval:
                    proposal.decision = "approved"
                run.proposals.append(proposal)
        self._event(
            run,
            "verifier",
            "verification_completed",
            f"Created {len(run.proposals)} evidence-backed repair proposals",
        )
        if any(item.decision == "approved" for item in run.proposals):
            self._save(run)
            return self.apply(run.id)
        run.status = RunStatus.AWAITING_REVIEW if run.proposals else RunStatus.COMPLETED
        if run.status == RunStatus.COMPLETED:
            tree = self._require_tree(run.tree_id)
            run.metrics_after = self._metrics(tree)
            self._event(
                run, "system", "audit_completed", "Audit completed with no supported repairs"
            )
        self._save(run)
        return run

    def _audit(self, tree: TreeSnapshot) -> list[Finding]:
        findings: list[Finding] = []
        person_ids = {person.get("id") for person in tree.people}
        normalized_names = Counter(
            str(person.get("name", "")).strip().casefold()
            for person in tree.people
            if person.get("name")
        )
        for person in tree.people:
            person_id = str(person.get("id", ""))
            if not person.get("sources"):
                findings.append(
                    Finding(
                        kind=FindingKind.MISSING_CITATION,
                        subject_id=person_id,
                        field="sources",
                        current_value=[],
                        description=f"Find reliable sources for {person.get('name', 'this person')}",
                        priority=90,
                    )
                )
            for field in CORE_FIELDS:
                if field != "deathDate" and not person.get(field):
                    findings.append(
                        Finding(
                            kind=FindingKind.MISSING_FACT,
                            subject_id=person_id,
                            field=field,
                            description=f"Research missing {field} for {person.get('name', 'this person')}",
                            priority=70,
                        )
                    )
            normalized = str(person.get("name", "")).strip().casefold()
            if normalized and normalized_names[normalized] > 1:
                findings.append(
                    Finding(
                        kind=FindingKind.POSSIBLE_DUPLICATE,
                        subject_id=person_id,
                        description=f"Review possible duplicate person: {person.get('name')}",
                        priority=40,
                    )
                )
        for relationship in tree.relationships:
            if (
                relationship.get("from") not in person_ids
                or relationship.get("to") not in person_ids
            ):
                findings.append(
                    Finding(
                        kind=FindingKind.DANGLING_RELATIONSHIP,
                        subject_id=str(relationship.get("from", "unknown")),
                        description="Relationship references a person missing from the tree",
                        priority=100,
                    )
                )
        return findings

    @staticmethod
    def _metrics(tree: TreeSnapshot) -> AuditMetrics:
        total = 0
        supported = 0
        for person in tree.people:
            for field in CORE_FIELDS:
                if person.get(field):
                    total += 1
                    if person.get("sources"):
                        supported += 1
        return AuditMetrics(
            people=len(tree.people),
            relationships=len(tree.relationships),
            total_claims=total,
            supported_claims=supported,
            evidence_score=round(supported / total, 3) if total else 0,
        )

    def _event(self, run: AuditRun, agent: str, event_type: str, message: str, data=None) -> None:
        run.events.append(
            AgentEvent(
                run_id=run.id, agent=agent, type=event_type, message=message, data=data or {}
            )
        )

    def _save(self, run: AuditRun) -> None:
        run.updated_at = utc_now()
        self.store.save_run(run)

    def _require_run(self, run_id: str) -> AuditRun:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError("Audit run not found")
        return run

    def _require_tree(self, tree_id: str) -> TreeSnapshot:
        tree = self.store.get_tree(tree_id)
        if not tree:
            raise KeyError("Tree snapshot not found")
        return tree
