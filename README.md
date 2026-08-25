# Rootstory Evidence Agent

Rootstory Evidence Agent is an autonomous, event-driven family-tree auditor. A user gives it an
outcome—strengthen the evidence behind an existing tree—and it plans research tasks, delegates
source discovery, verifies claims, proposes reversible repairs, pauses for consequential human
decisions, and re-audits the result.

This repository was created for the 2026 All Things Agentic hackathon. The existing Rootstory
application is the host platform; the evidence-audit workflow in this repository is new work.

## Workflow

1. `POST /v1/audits` snapshots a tree and queues an audit.
2. The planner detects missing citations, incomplete facts, duplicates, and broken relationships.
3. Research tasks persist independently so failures do not erase progress.
4. A Gemini specialist performs grounded research and returns structured claims with sources.
5. The verifier rejects unsupported/low-confidence claims and creates explicit patch proposals.
6. Low-risk additions may be auto-applied when the owner opts in. Replacements and destructive
   changes require review.
7. The repairer applies approved patches with a complete event trail and recalculates evidence
   coverage.

There is no chatbot. Rootstory presents this state machine as an audit dashboard and evidence
review queue.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn evidence_agent.main:app --reload
```

The safe local default uses `EVIDENCE_RESEARCHER=null`, which never fabricates evidence. Set
`EVIDENCE_RESEARCHER=gemini` with Vertex AI credentials to enable grounded Google Search.

## API

- `POST /v1/audits` — start an audit
- `GET /v1/audits/{runId}` — read current state, events, tasks, and proposals
- `POST /v1/internal/audits/{runId}/work` — execute one durable unit of work
- `POST /v1/audits/{runId}/proposals/{proposalId}/decision` — approve or reject
- `POST /v1/audits/{runId}/apply` — apply approved patches
- `GET /.well-known/agent.json` — agent discovery card

Use `EVIDENCE_STORE=firestore` and `WORK_DISPATCH=cloud_tasks` in production. Each Cloud Tasks
invocation performs one durable unit of research, persists the new state, and schedules the next
unit. A provider failure can therefore be retried without losing completed work.

Production uses Firebase ID-token verification (`AUTH_MODE=firebase`). Cloud Tasks sends both an
OIDC identity and a Secret Manager-backed worker credential to the internal work endpoint.
