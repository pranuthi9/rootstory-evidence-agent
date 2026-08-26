from __future__ import annotations

import os
import secrets

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agents import GeminiEvidenceResearcher, NullEvidenceResearcher
from .auth import authenticated_user
from .dispatch import CloudTasksDispatcher
from .engine import EvidenceEngine
from .models import DecisionRequest, RunStatus, StartAuditRequest
from .store import FirestoreEvidenceStore, MemoryEvidenceStore

app = FastAPI(title="Rootstory Evidence Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ],
    allow_origin_regex=os.getenv("ALLOWED_ORIGIN_REGEX") or None,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Rootstory-User"],
)
store = (
    FirestoreEvidenceStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    if os.getenv("EVIDENCE_STORE", "memory") == "firestore"
    else MemoryEvidenceStore()
)
researcher = (
    GeminiEvidenceResearcher()
    if os.getenv("EVIDENCE_RESEARCHER", "null") == "gemini"
    else NullEvidenceResearcher()
)
engine = EvidenceEngine(store, researcher)
dispatcher = CloudTasksDispatcher() if os.getenv("WORK_DISPATCH") == "cloud_tasks" else None


def require_owner(expected_owner: str, supplied_owner: str) -> None:
    if not supplied_owner or supplied_owner != expected_owner:
        raise HTTPException(status_code=403, detail="Tree owner authorization failed")


def run_until_pause(run_id: str) -> None:
    """Local runner; Cloud Tasks will invoke one durable work step per request in production."""
    run = engine.plan(run_id)
    while run.status in {RunStatus.RESEARCHING, RunStatus.VERIFYING}:
        run = engine.work_next(run_id)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "rootstory-evidence-agent",
        "model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        "researcher": os.getenv("EVIDENCE_RESEARCHER", "null"),
        "revision": os.getenv("K_REVISION", "local"),
    }


@app.get("/.well-known/agent.json")
def agent_card() -> dict:
    return {
        "name": "Rootstory Evidence Agent",
        "description": "Autonomously audits, researches, verifies, and repairs evidence gaps in family trees.",
        "version": "0.1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "skills": [
            {
                "id": "audit_family_tree_evidence",
                "name": "Audit Family Tree Evidence",
                "description": "Plans and delegates source research, verifies claims, and proposes reversible tree repairs.",
                "inputModes": ["application/json"],
                "outputModes": ["application/json"],
            }
        ],
    }


@app.post("/v1/audits", status_code=202)
def start_audit(
    request: StartAuditRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(authenticated_user),
):
    require_owner(request.tree.owner_id, user_id)
    run = engine.start(request.tree, request.auto_apply_safe)
    if dispatcher:
        dispatcher.dispatch(run.id)
    else:
        background_tasks.add_task(run_until_pause, run.id)
    return run


@app.get("/v1/audits/{run_id}")
def get_audit(run_id: str, user_id: str = Depends(authenticated_user)):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit run not found")
    require_owner(run.owner_id, user_id)
    return run


@app.post("/v1/internal/audits/{run_id}/work")
def work_audit(run_id: str, x_evidence_worker_token: str | None = Header(default=None)):
    """Perform one idempotent unit of work; intended for authenticated Cloud Tasks calls."""
    expected_token = os.getenv("EVIDENCE_WORKER_TOKEN")
    if dispatcher and (
        not expected_token
        or not x_evidence_worker_token
        or not secrets.compare_digest(expected_token, x_evidence_worker_token)
    ):
        raise HTTPException(status_code=401, detail="Invalid worker credential")
    try:
        run = store.get_run(run_id)
        if not run:
            raise KeyError
        result = engine.plan(run_id) if run.status == RunStatus.QUEUED else engine.work_next(run_id)
        if dispatcher and result.status in {RunStatus.RESEARCHING, RunStatus.VERIFYING}:
            dispatcher.dispatch(run_id)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Audit run not found") from exc


@app.post("/v1/audits/{run_id}/proposals/{proposal_id}/decision")
def decide_proposal(
    run_id: str,
    proposal_id: str,
    request: DecisionRequest,
    user_id: str = Depends(authenticated_user),
):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit run not found")
    require_owner(run.owner_id, user_id)
    try:
        return engine.decide(run_id, proposal_id, request.decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/audits/{run_id}/apply")
def apply_approved(run_id: str, user_id: str = Depends(authenticated_user)):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit run not found")
    require_owner(run.owner_id, user_id)
    applied = engine.apply(run_id)
    return {"run": applied, "tree": store.get_tree(applied.tree_id)}
