# Architecture

The Evidence Agent accepts one goal—strengthen an existing family tree—and owns the workflow
needed to reach it. Rootstory supplies identity, the selected tree snapshot, and human decisions;
it does not micromanage research prompts.

```mermaid
flowchart LR
  UI[Rootstory Evidence Audit UI] -->|Firebase ID token + tree snapshot| API[Cloud Run API]
  API --> FS[(Firestore audit state)]
  API --> Q[Cloud Tasks]
  Q -->|one durable work unit| P[Planner]
  Q --> R[Evidence Researcher]
  R -->|Gemini + Google Search grounding| V[Verifier]
  V --> X[Repair proposals]
  X -->|low-risk opt-in| A[Repairer]
  X -->|uncertain change| H[Human review]
  H --> A
  A --> FS
  FS --> UI
```

## Durable state machine

`queued → auditing → researching → verifying → awaiting_review → applying → completed`

Every research task has its own status and attempt count. A worker processes only one queued task,
writes its claims and event record, then schedules the next invocation. This bounds request length,
makes progress visible, and allows Cloud Tasks to retry provider failures safely.

## Mutation policy

- Researchers return claims and citations, never database mutations.
- The verifier rejects claims without canonical HTTPS sources or below the confidence threshold.
- Additive citation patches may be auto-applied only when the owner explicitly opts in.
- Replacements, merges, deletions, relationship changes, conflicts, and sensitive facts require
  human approval.
- Each proposal stores its previous value and sources, making the decision auditable and reversible.

