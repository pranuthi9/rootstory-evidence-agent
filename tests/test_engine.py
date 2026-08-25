from evidence_agent.engine import EvidenceEngine
from evidence_agent.evaluation import evaluate_run
from evidence_agent.models import Claim, RunStatus, Source, TreeSnapshot
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
