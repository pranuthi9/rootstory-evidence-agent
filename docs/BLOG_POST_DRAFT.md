# I Built an Autonomous Evidence Team for Family Trees

_How Rootstory Evidence Agent uses Gemini 3.5 Flash, Cloud Run, Cloud Tasks, and Firestore to turn
unsupported family-tree facts into source-backed, human-reviewed proposals._

> I created this article for the purpose of entering the All Things Agentic Hackathon.

I know my grandparents' names, but very little about the lives behind those names. Someone should
have written their stories down.

That absence inspired me to build Rootstory: a place where families can create and explore family
trees together, preserve photographs and stories, and make those memories available to the next
generation. I wanted families to experience moments like:

- “I never knew my grandfather did that.”
- “I found a story from a cousin I had never met.”
- “I discovered a connection between two branches of our family.”
- “I am preserving something my children can return to.”

Rootstory organizes those memories around people and relationships. Families can collaborate on a
private tree or publish selected history for others to explore. Photos, biographical details,
personal stories, and sources can give each person a life beyond a box in a diagram.

But building Rootstory exposed another problem.

## A complete-looking tree is not necessarily a trustworthy tree

A tree can contain dozens of people and still leave an important question unanswered: what
evidence supports these names, dates, and relationships?

Checking every person manually is slow and repetitive. Someone has to identify missing citations,
open many pages, compare claims, decide which sources are credible, and update the tree carefully.
One careless change can turn a guess into family history.

For the All Things Agentic Hackathon, I built a new system to handle that work: **Rootstory
Evidence Agent**.

Rootstory itself existed before the hackathon and serves as the host platform. The separately
deployed Evidence Agent, its durable research workflow, verification pipeline, review experience,
and Google Cloud infrastructure are the new hackathon project.

## Not a chatbot: an event-driven workflow

The user gives the agent one outcome:

> Strengthen the evidence behind this family tree.

The agent then owns the workflow:

1. It reads a snapshot of the whole tree and calculates evidence coverage.
2. A planner detects unsupported people, missing facts, possible duplicates, and broken
   relationship references.
3. It converts actionable gaps into independent, priority-ordered research tasks.
4. A research specialist investigates one person and one objective with Gemini 3.5 Flash and
   Google Search grounding.
5. A verifier rejects claims without usable sources or sufficient confidence.
6. The agent creates field-specific repair proposals with the person, prior value, proposed value,
   sources, confidence, and risk.
7. The tree owner opens the original sources and selects or rejects each discovery.
8. Only the selected fields are applied. Everything else remains unchanged.

There is no conversational loop requiring the user to guide every step. Rootstory shows a visible
journey from reading the tree, through searching and cross-checking, to human review. The user can
leave while the audit continues.

## Why the workflow is durable

A family tree can produce dozens of research objectives. Running all of them inside one request
would create a fragile, long-running operation vulnerable to timeouts, quota errors, and container
restarts.

Instead, the Evidence Agent uses a persisted state machine:

`queued → auditing → researching → verifying → awaiting_review → applying → completed`

The FastAPI service runs on Cloud Run. Cloud Tasks invokes an internal worker endpoint for one
durable unit at a time. Firestore stores the tree snapshot, findings, task statuses, attempt counts,
claims, proposals, and event history.

After each task, the new state is committed before the next task is dispatched. If Gemini returns a
transient error, the task can be retried without discarding completed research. If the user closes
the browser, the work continues. When the owner returns—even in a later session—Rootstory restores
the latest audit from the server.

## Gemini researches; it does not control the tree

The research specialist uses the Google Gen AI SDK to call Gemini 3.5 Flash through Vertex AI. It
requests structured claims for one person and one evidence gap at a time, with Google Search
grounding enabled.

The model never receives permission to write directly to the family tree.

That separation matters because a plausible URL is not automatically evidence. The production
path prefers grounding metadata returned by Google Search. If fallback URLs are evaluated, the
service accepts only public HTTPS pages, follows limited redirects, checks the response type, and
verifies that the page identifies the research subject.

The verifier then applies a confidence threshold. A claim without usable sources does not become a
proposal. For many private relatives, the correct outcome is no proposal at all.

## Human approval needs more than an Approve button

My first review screen exposed raw patch JSON and an ambiguous **Approve** action. Technically it
worked, but it did not answer the user's most important question: “What will happen to my tree?”

The current experience explains:

- The exact person affected
- The exact field that would change
- The source links supporting it
- What will remain unchanged
- Whether the discovery is selected but not yet saved

Selection and application are separate actions. A family can select one discovery, leave the rest
pending, and return later. The final apply action writes only the selected fields to the live tree.

For this kind of product, “human in the loop” is not a checkbox. The human must understand the
decision and remain in control of the mutation boundary.

## Architecture and security

![Rootstory Evidence Agent architecture](https://raw.githubusercontent.com/pranuthi9/rootstory-evidence-agent/main/docs/architecture.png)

The deployed system uses:

- **Gemini 3.5 Flash** on Vertex AI
- **Google Gen AI SDK**
- **Google Search grounding**
- **Cloud Run** for the FastAPI agent and worker endpoint
- **Cloud Tasks** for durable asynchronous work
- **Firestore** for audit runs, snapshots, events, tasks, and proposals
- **Firebase Authentication** to verify the tree owner
- **Firebase Hosting** for the Rootstory web experience
- **Secret Manager-backed credentials** for worker execution
- **GitHub Actions with Workload Identity Federation** for keyless Google Cloud deployment

The public API verifies the Firebase user and checks that the caller owns the tree. Cloud Tasks
sends an OIDC identity, while the internal endpoint also validates a separate worker credential.
The model proposes; the verifier gates; the owner decides; the repairer applies.

## What I learned

The hardest part of an agent is not producing an answer. It is owning a workflow safely over time.

Useful autonomy required:

- Durable state instead of a single long request
- Narrow, independently retryable tasks
- Source and confidence policy
- Identity and ownership checks
- Progress a non-technical user can understand
- Recovery across sessions
- A precise human-controlled mutation boundary

I began with a family-history problem: how do we preserve more than names before those stories
disappear? The Evidence Agent adds a second promise: the history families preserve should also be
something they can inspect and trust.

## Try it and inspect the code

- Hosted experience: [https://rootstory.app](https://rootstory.app)
- Evidence Agent repository:
  [https://github.com/pranuthi9/rootstory-evidence-agent](https://github.com/pranuthi9/rootstory-evidence-agent)
- Rootstory host application:
  [https://github.com/pranuthi9/rootstory](https://github.com/pranuthi9/rootstory)

In Rootstory, sign in, open a tree you own, and choose **Evidence Agent**. The public Evidence Agent
repository includes reproducible local tests, Cloud Run deployment instructions, the architecture
diagram, and the complete state-machine implementation.

_Built for the All Things Agentic Hackathon using Gemini and Google Cloud._
