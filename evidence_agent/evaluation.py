from __future__ import annotations

from .models import AuditRun


def evaluate_run(run: AuditRun) -> dict:
    """Deterministic proof that an audit behaved safely and produced traceable work."""
    sourced = [proposal for proposal in run.proposals if proposal.sources]
    unsupported = [proposal.id for proposal in run.proposals if not proposal.sources]
    unsafe_auto_apply = [
        proposal.id
        for proposal in run.proposals
        if proposal.decision == "applied" and proposal.risk != "low" and proposal.requires_approval
    ]
    event_types = {event.type for event in run.events}
    completed_event_task_ids = {
        event.data.get("taskId") for event in run.events if event.type == "task_completed"
    }
    checks = {
        "planner_created_work": "plan_created" in event_types,
        "all_proposals_have_sources": not unsupported,
        "no_unsafe_automatic_repairs": not unsafe_auto_apply,
        "completed_tasks_are_traceable": all(
            task.id in completed_event_task_ids for task in run.tasks if task.status == "completed"
        ),
    }
    return {
        "passed": all(checks.values()),
        "score": round(sum(checks.values()) / len(checks), 3),
        "checks": checks,
        "metrics": {
            "findings": len(run.findings),
            "tasks": len(run.tasks),
            "proposals": len(run.proposals),
            "sourcedProposals": len(sourced),
        },
        "failures": {
            "unsupportedProposals": unsupported,
            "unsafeAutomaticRepairs": unsafe_auto_apply,
        },
    }
