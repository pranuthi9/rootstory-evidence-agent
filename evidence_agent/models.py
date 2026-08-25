from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    QUEUED = "queued"
    AUDITING = "auditing"
    RESEARCHING = "researching"
    VERIFYING = "verifying"
    AWAITING_REVIEW = "awaiting_review"
    APPLYING = "applying"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FindingKind(StrEnum):
    MISSING_CITATION = "missing_citation"
    MISSING_FACT = "missing_fact"
    DANGLING_RELATIONSHIP = "dangling_relationship"
    CONFLICT = "conflict"
    POSSIBLE_DUPLICATE = "possible_duplicate"


class Source(BaseModel):
    title: str
    url: HttpUrl
    publisher: str | None = None
    accessed_at: datetime = Field(default_factory=utc_now)


class Claim(BaseModel):
    subject_id: str
    field: str
    value: Any
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rationale: str


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: FindingKind
    subject_id: str
    field: str | None = None
    current_value: Any = None
    description: str
    priority: int = Field(default=50, ge=0, le=100)


class ResearchTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    finding_id: str
    subject_id: str
    objective: str
    status: TaskStatus = TaskStatus.QUEUED
    attempt_count: int = 0
    claims: list[Claim] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PatchOperation(BaseModel):
    operation: Literal["add", "replace", "flag"]
    path: str
    value: Any = None
    previous_value: Any = None


class Proposal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    finding_id: str
    subject_id: str
    summary: str
    patch: PatchOperation
    sources: list[Source]
    confidence: float = Field(ge=0, le=1)
    risk: Literal["low", "medium", "high"]
    requires_approval: bool = True
    decision: Literal["pending", "approved", "rejected", "applied"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)


class AgentEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    agent: Literal["planner", "researcher", "verifier", "repairer", "system"]
    type: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AuditMetrics(BaseModel):
    people: int = 0
    relationships: int = 0
    total_claims: int = 0
    supported_claims: int = 0
    evidence_score: float = 0


class AuditRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tree_id: str
    owner_id: str
    status: RunStatus = RunStatus.QUEUED
    auto_apply_safe: bool = False
    metrics_before: AuditMetrics = Field(default_factory=AuditMetrics)
    metrics_after: AuditMetrics | None = None
    findings: list[Finding] = Field(default_factory=list)
    tasks: list[ResearchTask] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TreeSnapshot(BaseModel):
    id: str
    owner_id: str
    people: list[dict[str, Any]]
    relationships: list[dict[str, Any]]


class StartAuditRequest(BaseModel):
    tree: TreeSnapshot
    auto_apply_safe: bool = False


class DecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
