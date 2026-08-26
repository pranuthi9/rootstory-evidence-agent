# Four-minute demo script

## Recording goal

Show a real autonomous workflow, real evidence, human control, and proof that the backend is
deployed on Google Cloud. Do not spend the video navigating every Rootstory feature.

Record at 1080p with browser zoom around 90–100%. Prepare one completed audit for reliable review
footage and a second tree for the live start. Keep the Cloud Console tabs open before recording.

## 0:00–0:35 — Rootstory's origin and the human problem

**Visual:** Begin on Rootstory. Move briefly through a family tree, its family album, and a person or
story view. End on a tree with the **Evidence Agent** entry point visible.

**Narration:**

> I know my grandparents' names, but very little about the lives behind them. Someone should have
> written those stories down. That inspired me to build Rootstory, where families can create trees
> together and preserve the photos, stories, and discoveries behind each person—not only names and
> dates. Rootstory existed before this hackathon, and it became the real host platform for the new
> agent I built here.

## 0:35–0:55 — The problem Rootstory exposed

**Visual:** Pause on several people in a researched tree, then open **Evidence Agent**.

**Narration:**

> As these trees grew, I found a second problem: a tree can look complete while many people and
> facts still have no evidence. Checking every profile and source manually takes hours. Families
> should not have to choose between an engaging story and a trustworthy record.

## 0:55–1:10 — Give the agent a goal

**Visual:** Open **Evidence Agent** on the prepared live-start tree. Show the introductory state,
then start the check.

**Narration:**

> This is not a chatbot. I give it one outcome: strengthen the evidence behind this tree. The agent
> reads the whole tree, identifies gaps, creates research tasks, and continues while I leave the
> page.

## 1:10–1:40 — Autonomous execution

**Visual:** Show the journey steps, current person, progress counters, and several changing agent
activities. Briefly navigate back to the tree and return to show recovery if timing permits.

**Narration:**

> The planner audits people, core facts, citations, duplicates, and relationship references. Each
> actionable gap becomes a separate persisted task. Cloud Tasks sends one unit of work to Cloud Run
> at a time. Gemini 3.5 Flash researches one person and objective with Google Search grounding, and
> the verifier rejects claims without sufficient confidence and usable sources. Progress is stored
> after every task, so a quota error or container restart does not erase completed research.

## 1:40–2:20 — Human-controlled evidence review

**Visual:** Switch to the prepared completed audit. Open one source in a new tab, return, show the
exact affected person and field, select one proposal, leave another pending, and show the final
apply tray. Apply only the selected evidence.

**Narration:**

> The agent does not silently rewrite family history. It returns a proposal that names the person,
> the exact field, the source links, and what will remain unchanged. Selecting evidence still does
> not modify the tree. Only this separate final action applies the selected fields. I can review one
> discovery now, leave the others pending, and come back later.

## 2:20–2:40 — Result in the tree

**Visual:** Return to the affected person's profile in the tree and show the newly attached source.

**Narration:**

> The approved source is now attached to this person's profile, where the family can revisit it.
> Names, dates, biographies, and relationships that were not part of the proposal remain untouched.

## 2:40–3:25 — Prove the Google Cloud backend

**Visual:** Google Cloud Console tabs, in this order:

1. Cloud Run service `rootstory-evidence-agent`, showing the green deployed revision and service URL.
2. Cloud Tasks queue `rootstory-evidence-audits`, showing dispatched tasks.
3. Firestore collections `evidenceAuditRuns` and `evidenceTreeSnapshots`, showing a run's status,
   tasks, proposals, and events without exposing personal data or credentials.
4. Cloud Run logs showing real requests to `/v1/internal/audits/.../work` and the deployed revision.

**Narration:**

> The backend is running on Google Cloud. Cloud Run hosts the FastAPI agent. Cloud Tasks provides
> durable asynchronous execution. Firestore stores runs, snapshots, tasks, events, and proposals.
> Gemini 3.5 Flash runs through Vertex AI using the Google Gen AI SDK and Google Search grounding.
> Firebase verifies the tree owner. Cloud Tasks sends an OIDC identity, and the internal worker
> validates a separate worker credential before accepting work.

## 3:25–3:45 — Architecture

**Visual:** Full-screen architecture diagram from `docs/architecture.png` or the Mermaid diagram in
`docs/ARCHITECTURE.md`.

**Narration:**

> The key design is separation of authority. The model can research and propose, but it cannot write
> directly to the family tree. The verifier creates field-specific proposals, the owner decides,
> and the repairer applies only approved fields.

## 3:45–4:00 — Close

**Visual:** Completed Evidence Agent screen with applied and pending discoveries.

**Narration:**

> Rootstory Evidence Agent gives a family tree its own evidence team: autonomous enough to do the
> heavy research, durable enough to finish, and careful enough to leave family history in human
> hands.

## Recording checklist

- Keep the final cut at or below 4:00.
- Show the Cloud Run URL or service page clearly enough to prove deployment.
- Use real live data; do not imply that a staged completed audit is running in real time.
- Hide tokens, environment variables, billing details, email addresses, and private family data.
- Open at least one real source so the evidence is visible.
- Show one proposal being applied and another remaining pending.
- Avoid waiting through the full audit; use a prepared completed run for the review segment.
- Add captions for the product name, Google Cloud components, and final value proposition.
