# Rootstory Evidence Agent — Devpost Submission Copy

## Elevator pitch — 192 characters

Rootstory Evidence Agent autonomously audits family trees, researches unsupported people with
Gemini, verifies sources, and proposes reversible, human-approved repairs—while families carry on.

## Category

**The Taskmaster**

Rootstory Evidence Agent is an event-driven workflow, not a chatbot. Given the goal of
strengthening an existing family tree, it audits the tree, plans and routes independent research
tasks, persists progress, verifies evidence, and returns field-specific repairs for human review.

## Project to share

- **Project title:** Rootstory Evidence Agent
- **Hosted project:** [https://rootstory.app](https://rootstory.app)
- **Hackathon agent repository:**
  [github.com/pranuthi9/rootstory-evidence-agent](https://github.com/pranuthi9/rootstory-evidence-agent)
- **Host application repository:**
  [github.com/pranuthi9/rootstory](https://github.com/pranuthi9/rootstory)
- **Cloud Run service:** `rootstory-evidence-agent` in Google Cloud project `rootstory`

For judging, sign in to the hosted project, open a family tree you own, and select **Evidence
Agent**. The separate agent repository contains the new hackathon workflow. Rootstory existed
before the hackathon and is disclosed as the host platform.

## About the project

### Inspiration

I know my grandparents' names, but very little about the lives behind those names. Someone should
have written their stories down. I started Rootstory to make that easier for families today, so the
next generation does not inherit the same gaps.

But preserving family history introduces another problem: a family tree can look complete while
many of its people, dates, and relationships have little or no evidence. Checking every person is
slow, repetitive work. It requires finding gaps, opening many sources, deciding which claims are
credible, and carefully updating the tree without turning a guess into family history.

That is the job I built Rootstory Evidence Agent to handle.

### What it does

The owner gives the agent one outcome: **strengthen the evidence behind this family tree**. From
there, the agent runs a complete asynchronous workflow:

1. It reads a snapshot of the whole tree and calculates its evidence coverage.
2. A planner identifies unsupported people, missing facts, possible duplicates, and broken
   relationship references.
3. It converts actionable gaps into independent research tasks and orders them by priority.
4. A research specialist investigates one person and one objective at a time with Gemini 3.5 Flash
   and Google Search grounding.
5. A verifier rejects claims without usable sources or sufficient confidence.
6. The agent creates explicit repair proposals containing the person, field, prior value, proposed
   value, sources, confidence, and risk.
7. The tree owner opens the original sources and selects or rejects each discovery.
8. Only the selected fields are applied. Unreviewed work remains available for later.

The user can leave while the audit runs. Cloud Tasks processes one durable unit at a time, and
Firestore preserves completed work, attempts, events, and proposals. If a model call fails or a
Cloud Run instance stops, the next invocation resumes from persisted state instead of restarting
the entire tree.

There is no chat box. The experience is a visible journey from reading the tree, through searching
and cross-checking, to a human-controlled evidence review.

### How I built it

I created the Evidence Agent as a separate Python service with FastAPI and the Google Gen AI SDK.
It runs on Cloud Run and uses a durable state machine:

`queued → auditing → researching → verifying → awaiting_review → applying → completed`

Cloud Tasks invokes an internal worker endpoint for one work unit at a time. Audit runs, tree
snapshots, findings, tasks, claims, proposals, and event history are persisted in Firestore. Gemini
3.5 Flash runs through Vertex AI with Google Search grounding. The researcher returns structured
claims; it never receives permission to mutate the family tree directly.

The verifier enforces source and confidence policy before a claim becomes a proposal. Rootstory's
React interface polls the saved run, translates technical activity into understandable progress,
and makes the final mutation boundary explicit: selecting evidence does not change the tree; the
owner must perform a separate apply action.

Firebase Authentication protects owner operations. Cloud Tasks calls the internal worker with an
OIDC identity and a separate Secret Manager-backed worker credential; the worker endpoint validates
the credential before processing work. GitHub Actions uses Workload Identity Federation to test and
deploy without storing a downloadable Google Cloud key.

### Challenges

**Long-running research exceeded ordinary request boundaries.** A large tree can produce dozens of
research objectives. I changed the workflow from one long request into independently persisted
tasks dispatched through Cloud Tasks.

**Model and provider limits are normal, not exceptional.** Gemini can return quota or transient
errors. Each task stores an attempt count and completed work is committed before the next task, so
retries do not erase progress.

**A citation is not automatically evidence.** Generated URLs cannot be trusted simply because they
look plausible. The production path prefers grounding metadata returned by Google Search. Fallback
pages must be public HTTPS resources, survive redirects, return suitable content, and identify the
research subject.

**Human approval had to be understandable.** Early proposal cards exposed raw patch JSON and an
ambiguous “Approve” button. The current interface names the affected person, explains the exact
field that will change, states what will not change, separates selection from application, and
restores unfinished audits across sessions.

**Existing product versus hackathon work needed honest boundaries.** Rootstory is an existing host
application. The separately deployed Evidence Agent, durable workflow, research and verification
pipeline, review experience, and Cloud infrastructure described here are the hackathon project.

### What I learned

The hardest part of an agent is not producing an answer. It is owning a workflow safely over time.
Useful autonomy required durable state, narrow task boundaries, retry behavior, identity checks,
source verification, observable progress, and a clear point where a human remains in control.

I also learned that “human in the loop” is not satisfied by adding an approval button. The user
must understand what approval means, which data will change, and whether they can leave and return
without losing work.

### Features and functionality

- Whole-tree evidence audit and coverage metrics
- Priority-based planning across people and missing fields
- Durable asynchronous research through Cloud Tasks
- Gemini 3.5 Flash research with Google Search grounding
- Server-side fallback source validation and confidence filtering
- Persisted task attempts, findings, events, claims, and proposals
- Live, non-chat progress experience in Rootstory
- Field-specific proposals with original sources
- Human selection followed by a separate apply boundary
- Partial review and cross-session audit recovery
- Firebase owner authentication and credential-protected worker execution
- Agent discovery card at `/.well-known/agent.json`

### Technologies used

- Gemini 3.5 Flash on Vertex AI
- Google Gen AI SDK
- Google Search grounding
- Cloud Run
- Cloud Tasks
- Firestore
- Firebase Authentication and Firebase Hosting
- Secret Manager-backed worker credential
- Python, FastAPI, Pydantic, HTTPX
- React, TypeScript, Vite
- GitHub Actions and Google Cloud Workload Identity Federation

### Other data sources

The agent researches publicly accessible web sources surfaced through Google Search grounding. It
stores canonical source titles, publishers, and URLs with each proposal so the reviewer can inspect
the evidence directly. It does not treat model-generated text as a source.

### Current limitations

- Audit actions are currently restricted to the tree owner.
- The interface restores the latest audit for a tree; a complete audit-history page is planned.
- Decisions are intentionally conservative, but an undo/defer control for individual review
  decisions is still planned.
- Public web evidence is much richer for notable people than for private relatives; the correct
  result for many people is therefore no proposal.

## One-sentence credit-request answer

**Track: The Taskmaster.** I am building Rootstory Evidence Agent, an event-driven agent that audits
an existing family tree, delegates source research to Gemini, verifies evidence, and prepares
reversible repairs for the tree owner to approve while durable Google Cloud tasks run in the
background.
