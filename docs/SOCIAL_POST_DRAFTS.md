# Social post drafts

## Recommended LinkedIn post

I know my grandparents' names, but very little about the lives behind them. That gap inspired me to
build Rootstory, where families can create trees together and preserve the stories and photos behind
the names.

Building it exposed a second problem: a family tree can look complete while many people and facts
still have no reliable evidence.

For the All Things Agentic Hackathon, I built **Rootstory Evidence Agent**—an autonomous,
event-driven evidence team for family trees.

It:

🔎 audits an entire tree for unsupported people and missing facts  
🧭 plans and prioritizes independent research tasks  
✨ researches with Gemini 3.5 Flash and Google Search grounding  
✅ verifies sources and confidence before proposing anything  
⏳ runs asynchronously through Cloud Tasks and preserves progress in Firestore  
🛡️ shows the exact person and field affected before a human approves a change

It is not a chatbot, and Gemini cannot write directly to the family tree. The model researches, the
verifier gates, the family decides, and only approved fields are applied.

Rootstory is the existing host platform; the separately deployed Evidence Agent and its Google
Cloud workflow are my new hackathon project.

Built with the Google Gen AI SDK, Gemini 3.5 Flash on Vertex AI, Google Search grounding, Cloud Run,
Cloud Tasks, Firestore, Firebase Authentication, and Firebase Hosting.

Try it: https://rootstory.app  
Code: https://github.com/pranuthi9/rootstory-evidence-agent

#AllThingsAgenticHackathon #Gemini #GoogleCloud #AIagents #FamilyHistory

## Short X post

Family trees can look complete while facts lack evidence. I built Rootstory Evidence Agent to audit
a tree, research gaps with Gemini 3.5 Flash, verify sources, and propose human-approved repairs.

https://github.com/pranuthi9/rootstory-evidence-agent

#AllThingsAgenticHackathon

## X thread

### Post 1

I know my grandparents' names, but little about the lives behind them. That inspired Rootstory—a
place for families to preserve trees, photos, and stories together.

Now I built its autonomous evidence team for the #AllThingsAgenticHackathon 🧵

### Post 2

A family tree can look complete while many facts have no evidence. Checking every person manually
means finding gaps, searching sources, comparing claims, and carefully updating the tree.

Rootstory Evidence Agent owns that workflow.

### Post 3

It audits the whole tree, plans independent research tasks, investigates one person and objective at
a time with Gemini 3.5 Flash + Google Search grounding, and rejects claims without usable sources or
enough confidence.

### Post 4

This is not a chatbot. Cloud Tasks runs one durable unit at a time on Cloud Run. Firestore preserves
tasks, attempts, events, and proposals, so users can leave and return without losing the audit.

### Post 5

Gemini cannot write directly to the family tree. The agent shows the exact person, field, source,
and proposed change. The owner decides, and only selected fields are applied.

Try it: https://rootstory.app

Code: https://github.com/pranuthi9/rootstory-evidence-agent

## Optional launch caption for the demo video

What if every family tree had its own evidence team?

Rootstory Evidence Agent autonomously finds unsupported people, delegates research to Gemini 3.5
Flash, verifies public sources, and brings precise, reversible discoveries back to the family for
review.

The workflow runs on Cloud Run, Cloud Tasks, and Firestore—and it keeps working when the browser is
closed.

I built this project for the All Things Agentic Hackathon.

Watch the four-minute demo: [PUBLIC VIDEO URL]

#AllThingsAgenticHackathon #Gemini #GoogleCloud #AIagents
