Prompted for the resume storage layer (`ResumeStorage` interface, local-disk implementation, validation, tests).

AI miss: when asked for the next prompt, the AI suggested building the lead data layer (model, repository, schemas) without checking the repo. Those were already committed. Only `EmailEvent` was actually missing.

Follow-up gap spotted by the user: the resume layer was built, but the `LeadService` that ties it together (store the resume, create the lead, enforce PENDING -> REACHED_OUT) does not exist yet. The next prompt should have been about that, so this needs to be done next.

Feedback: check the codebase for what already exists before proposing the next step.


Follow-up prompt: `LeadService` (service only, no router, email sending or EmailEvent). Covers `create_lead`, `get_lead`, `list_leads` (optional state filter) and `mark_reached_out`, with domain exceptions `LeadNotFoundError` and `InvalidStateTransitionError` instead of `HTTPException`. This closes the gap noted above: the service ties the resume storage, the lead data access and the PENDING -> REACHED_OUT rule together.

Decisions the AI made that were not in the prompt or design:
- `resume_filename` is accepted per the requested signature but never used. The `Lead` model has no column for it and the stored name is server-generated. Needs the user's call: drop the parameter, or add a column later.
- If saving the lead fails after the resume was stored, the service deletes the stored file so no orphan is left behind.
- The service commits (the data access only flushes), so the email rows can join the same transaction later.
- `list_leads` returns `(leads, total)` and takes `limit`/`offset`, not page numbers; the router will convert and bound them.
- Known limit: `mark_reached_out` checks the state and then writes, so two attorneys acting at the same instant could both pass the check. Fix later with a conditional update in the data access if it matters.

Tests: 12 new, negative cases first (invalid resume creates nothing, storage cleanup on DB failure, unknown lead, repeated transition keeps the first attorney) plus one happy path per operation. Full suite: 32 passing.
