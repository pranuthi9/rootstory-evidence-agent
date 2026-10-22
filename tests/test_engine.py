import pytest

from evidence_agent.engine import EvidenceEngine
from evidence_agent.evaluation import evaluate_run
from evidence_agent.models import Claim, RunStatus, Source, TaskStatus, TreeSnapshot
from evidence_agent.store import MemoryEvidenceStore


class FakeResearcher:
    def research(self, person, finding):
        if finding.field == "sources":
            return [
                Claim(
                    subject_id=person["id"],
                    field="sources",
                    value=[
                        {
                            "title": "Example archive",
                            "url": "https://example.org/archive/person-1",
                            "publisher": "Example Archive",
                        }
                    ],
                    sources=[
                        Source(
                            title="Example archive",
                            url="https://example.org/archive/person-1",
                            publisher="Example Archive",
                        )
                    ],
                    confidence=0.96,
                    rationale="The archive directly identifies the subject.",
                ),
                Claim(
                    subject_id=person["id"],
                    field="birthDate",
                    value="1901-01-01",
                    sources=[
                        Source(
                            title="Example archive",
                            url="https://example.org/archive/person-1",
                        )
                    ],
                    confidence=0.99,
                    rationale="Out-of-scope claim returned by a misbehaving specialist.",
                ),
            ]
        return []


def sample_tree():
    return TreeSnapshot(
        id="tree-1",
        owner_id="user-1",
        people=[{"id": "person-1", "name": "Ada Example", "birthDate": "1900-01-01"}],
        relationships=[],
    )


def run_to_pause(engine, run_id):
    run = engine.plan(run_id)
    while run.status in {RunStatus.RESEARCHING, RunStatus.VERIFYING}:
        run = engine.work_next(run_id)
    return run


def test_planner_creates_prioritized_evidence_tasks():
    store = MemoryEvidenceStore()
    engine = EvidenceEngine(store, FakeResearcher())
    run = engine.start(sample_tree())

    planned = engine.plan(run.id)

    assert planned.status == RunStatus.RESEARCHING
    assert planned.findings[0].kind == "missing_citation"
    assert len(planned.tasks) >= 2
    assert planned.events[-1].agent == "planner"


def test_full_workflow_pauses_for_human_review_then_applies_patch():
    store = MemoryEvidenceStore()
    engine = EvidenceEngine(store, FakeResearcher())
    run = engine.start(sample_tree())

    reviewed = run_to_pause(engine, run.id)

    assert reviewed.status == RunStatus.AWAITING_REVIEW
    assert len(reviewed.proposals) == 1
    proposal = reviewed.proposals[0]
    assert proposal.sources[0].url.scheme == "https"

    engine.decide(run.id, proposal.id, "approved")
    completed = engine.apply(run.id)

    assert completed.status == RunStatus.COMPLETED
    assert completed.proposals[0].decision == "applied"
    assert store.get_tree("tree-1").people[0]["sources"]
    assert any(event.type == "patch_applied" for event in completed.events)
    assert evaluate_run(completed)["passed"] is True


def test_safe_addition_can_be_applied_without_review_when_enabled():
    store = MemoryEvidenceStore()
    engine = EvidenceEngine(store, FakeResearcher())
    run = engine.start(sample_tree(), auto_apply_safe=True)

    completed = run_to_pause(engine, run.id)

    assert completed.status == RunStatus.COMPLETED
    assert completed.proposals[0].decision == "applied"


def test_dangling_relationship_is_flagged_but_not_silently_deleted():
    tree = sample_tree()
    tree.relationships.append({"id": "r1", "type": "parent", "from": "missing", "to": "person-1"})
    store = MemoryEvidenceStore()
    engine = EvidenceEngine(store, FakeResearcher())
    run = engine.start(tree)

    planned = engine.plan(run.id)

    assert any(finding.kind == "dangling_relationship" for finding in planned.findings)
    assert store.get_tree("tree-1").relationships == tree.relationships


def test_planner_caps_paid_tasks_and_keeps_all_findings_in_stable_priority_order():
    tree = TreeSnapshot(
        id="large-tree",
        owner_id="owner",
        people=[{"id": f"person-{index}"} for index in range(30)],
        relationships=[],
    )
    engine = EvidenceEngine(MemoryEvidenceStore(), FakeResearcher())
    planned = engine.plan(engine.start(tree).id)

    assert len(planned.findings) == 120
    assert len(planned.tasks) == 20
    assert [task.subject_id for task in planned.tasks] == [f"person-{index}" for index in range(20)]
    findings_by_id = {finding.id: finding for finding in planned.findings}
    assert all(findings_by_id[task.finding_id].priority == 90 for task in planned.tasks)
    deferred = next(event for event in planned.events if event.type == "research_deferred")
    assert deferred.data == {"deferredFindings": 100, "taskBudget": 20}


def test_always_failing_provider_cannot_exceed_sixty_attempts_per_audit():
    class FailingResearcher:
        calls = 0

        def research(self, person, finding):
            self.calls += 1
            raise RuntimeError("provider unavailable")

    researcher = FailingResearcher()
    engine = EvidenceEngine(MemoryEvidenceStore(), researcher)
    tree = TreeSnapshot(
        id="large-tree",
        owner_id="owner",
        people=[{"id": str(index), "name": "Example"} for index in range(500)],
        relationships=[],
    )
    completed = run_to_pause(engine, engine.start(tree).id)

    assert researcher.calls == 60
    assert len(completed.tasks) == 20
    assert all(
        task.attempt_count == 3 and task.status == TaskStatus.FAILED for task in completed.tasks
    )
    assert completed.status == RunStatus.COMPLETED


def test_crash_recovery_stops_after_three_persisted_provider_attempts():
    class WorkerCrash(BaseException):
        pass

    class CrashingResearcher:
        calls = 0

        def research(self, person, finding):
            self.calls += 1
            raise WorkerCrash()

    store = MemoryEvidenceStore()
    researcher = CrashingResearcher()
    engine = EvidenceEngine(store, researcher)
    tree = sample_tree()
    tree.people[0]["birthPlace"] = "London"
    run = engine.plan(engine.start(tree).id)
    assert len(run.tasks) == 1

    for _ in range(3):
        with pytest.raises(WorkerCrash):
            EvidenceEngine(store, researcher).work_next(run.id)

    completed = EvidenceEngine(store, researcher).work_next(run.id)
    assert researcher.calls == 3
    assert completed.tasks[0].attempt_count == 3
    assert completed.tasks[0].status == TaskStatus.FAILED
    assert completed.status == RunStatus.COMPLETED
    engine.work_next(run.id)
    assert researcher.calls == 3


def test_exhausted_running_task_preserves_the_next_queued_task():
    class CountingResearcher:
        calls = 0

        def research(self, person, finding):
            self.calls += 1
            return []

    store = MemoryEvidenceStore()
    researcher = CountingResearcher()
    engine = EvidenceEngine(store, researcher)
    run = engine.plan(engine.start(sample_tree()).id)
    assert len(run.tasks) == 2
    run.tasks[0].status = TaskStatus.RUNNING
    run.tasks[0].attempt_count = 3
    store.save_run(run)

    resumed = engine.work_next(run.id)
    assert researcher.calls == 0
    assert resumed.tasks[0].status == TaskStatus.FAILED
    assert resumed.tasks[1].status == TaskStatus.QUEUED
    assert resumed.status == RunStatus.RESEARCHING
    completed = engine.work_next(run.id)
    assert researcher.calls == 1
    assert completed.status == RunStatus.COMPLETED
