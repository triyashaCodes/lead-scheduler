# How I Used a Coding Agent

**Tools.** I used Claude Code in the Claude desktop app (Claude Sonnet 5), along with its `frontend-design` skill and built-in browser for testing the UI against the running backend. I also used `pytest` for the backend test suite, which ended up with 159 tests.

**What I delegated.** I delegated most of the implementation work to the agent: project scaffolding, the data layer, resume storage, services, API routers, email integration, Google token verification, and both frontends. For this project, that was mostly repetitive implementation work, so I found it more useful to have the agent produce a first version and spend my time reviewing the design and behavior. I gave it a written spec for each step and asked it to explain the tradeoffs before implementing anything. The main design decisions are documented in `docs/Decisions.MD`, with the overall architecture in `docs/Design.md`.

**What I handled myself.** I made the architecture and product decisions, including the stack, layering, SQLite, Google SSO, keeping storage concerns out of `services/`, and requiring confirmation before marking a lead as reached out. I also renamed and reorganized parts of the data layer by hand. I set up the Google OAuth client and Gmail app password myself, so no credentials were ever given to the agent.

**Where the agent got it wrong.** I caught two issues that were not obvious from the initial test results.

First, the agent initially created the email records inside `send_lead_emails`, after the lead had already been saved. The tests passed, but this meant a crash between those two operations could leave a lead in the database with no record that its emails still needed to be sent. I changed this so `create_lead` creates the `PENDING` email records in the same transaction as the lead. I also added tests covering a failed save and repeated sends.

Second, `mark_reached_out` originally read the lead state, checked that it was `PENDING`, and then updated it. The agent had actually noted this as a limitation, but the implementation was still shipped because the tests were all sequential. I did a small concurrent test with two attorney requests and reproduced the race: both requests returned 200 and the second one overwrote `reached_out_by`. I changed the update to a single conditional `UPDATE ... WHERE state = 'PENDING'`, so only one request can make the transition and the other receives a 409. The new concurrency test fails against the old implementation (`['ok', 'ok']`) and passes with the fix.
