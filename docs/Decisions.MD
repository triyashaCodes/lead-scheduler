# Decisions

Status: **Decided** = confirmed by the user. **Proposed** = recommended in the design review, not yet explicitly confirmed.

Each entry lists what was chosen, why, and which alternatives lost and why.

## Auth: Decided
- Google SSO (hosted OIDC) instead of our own auth service; FastAPI only verifies the Google-issued JWT.
- Authorization is a separate attorney email allowlist from env config, so a valid Google login alone grants no access.
- Identity never travels in a request body: the token goes in the `Authorization` header only, and the caller is derived server-side from the verified token (e.g. `reached_out_by`), so no schema has a user or credential field.

**Why:** Attorneys handle prospects' personal data and resumes. Password storage, reset flows and MFA are security-sensitive and easy to get wrong, so we delegate them to Google. The allowlist is separate because "has a Google account" says nothing about "is one of our attorneys". Deriving identity from the token means a client can never claim to be someone else, and audit fields like `reached_out_by` are trustworthy.

**Rejected:**
- *Own email/password auth:* more code, more attack surface, and password handling we would have to maintain, for no user benefit.
- *Any valid Google login is enough:* would let any Google user read leads.
- *User id or email in the request body:* trivially spoofable and breaks the audit trail.

## Database: Decided
- SQLite via SQLAlchemy, per the original stack; path comes from `DATABASE_URL`, not code.
- Postgres is the production upgrade path (concurrent writes, row locking for email retries); the data-access layer keeps that swap small.

**Why:** SQLite needs no server, so setup and tests stay trivial, which fits the size of this project. It was also the specified stack. Routing all queries through `data_acceses` and configuring the URL via env means moving to Postgres later touches config and a few queries rather than the whole app.

**Rejected:**
- *Postgres from day one:* better concurrency, but extra infrastructure that the current load does not justify.
- *Hardcoded DB path:* violates the config rule and blocks the Postgres swap.

## Email tracking: Decided
- `email_events` is a core entity: rows are written `PENDING` in the same transaction as the lead, then updated to `SENT` or `FAILED`.
- `SENT` means accepted by the provider, not delivered; delivery and bounce webhooks are a production item.

**Why:** Writing the `PENDING` row in the same transaction as the lead guarantees that a lead can never exist without a record of the email owed for it, so a crash between the two cannot silently drop a notification. `FAILED` rows give the retry sweep something to find. Calling `SENT` "accepted, not delivered" avoids overstating what we know.

**Rejected:**
- *Fire-and-forget send with no record:* failures would be invisible and unrecoverable.
- *Only a `sent` boolean on the lead:* cannot represent failure, retries or history, and mixes email concerns into the lead.
- *Full delivery tracking now:* needs provider webhooks; deferred as a production item.

## Resume storage: Proposed
- Files live outside the DB behind a `ResumeStorage` interface (local disk now, S3 in production); the DB holds only key and metadata.
- Downloads go through an authenticated endpoint only; validate type by magic bytes and cap size via env.

**Why:** Blobs in SQLite bloat the file and slow backups. An interface lets local disk serve dev and S3 serve production without touching business logic. Resumes are personal data, so they are never served as public static files. Magic-byte checks are used because the filename and `Content-Type` are client-controlled and can lie.

**Rejected:**
- *Resume as a BLOB column:* simplest, but does not scale and complicates the Postgres move.
- *Serving from a public static directory:* anyone with a URL could read a resume.
- *Trusting extension or MIME header:* trivially spoofed.

## Email delivery: Proposed
- `EmailService` interface with SMTP (Mailhog in dev); the attorney email carries a link to the lead, not the resume attachment.
- FastAPI `BackgroundTasks` plus a retry sweep over `email_events` now; a queue and worker in production.

**Why:** SMTP with Mailhog lets us test the full flow locally with no external account or secrets, and the interface keeps a real provider swappable. A link instead of an attachment means the resume is only reachable after authentication and stays out of inboxes. `BackgroundTasks` keeps the public POST fast and adds no new infrastructure; the retry sweep covers its weakness (tasks are lost if the process dies), and a queue is the proper fix once volume warrants it.

**Rejected:**
- *Sending inline in the request:* a slow or failing mail server would slow or fail lead submission.
- *Attaching the resume:* bypasses our access control and copies personal data into mailboxes.
- *Celery/Redis queue now:* right eventually, but heavy for the current scale.
- *A specific email vendor SDK directly:* couples business code to a vendor and needs real credentials in dev.

## Lead state machine: Proposed
- `PENDING` -> `REACHED_OUT` only, set manually by an attorney; the service enforces it and records `reached_out_at` and `reached_out_by`.
- Repeating the transition returns 409 rather than silently succeeding.

**Why:** The requirement is a two-state lifecycle, so a minimal machine avoids speculative states. Enforcing it in the service keeps the rule independent of HTTP. A 409 on repeat preserves the original `reached_out_at`/`reached_out_by`; a silent success could overwrite them or hide two attorneys acting on the same lead.

**Rejected:**
- *Extra states (contacted, closed, etc.):* not requested; add when needed.
- *Idempotent success on repeat:* looks friendlier but blurs who reached out first.
- *Automatic transition when the email is sent:* the email being sent does not mean an attorney contacted the prospect.

## API shape: Proposed
- `PATCH /api/leads/{id}` accepting only `state`, and a single multipart `POST /api/leads` for public submission.
- Public POST gets a size cap and a honeypot field now; rate limiting and CAPTCHA are production items.

**Why:** PATCH with only `state` cannot be used to edit lead details or identity fields, which keeps the surface tiny. A single multipart POST lets the form submit lead data and resume atomically, so there is no orphaned upload or half-created lead. The public endpoint is unauthenticated by design, so cheap protections (size cap, honeypot) go in now and heavier ones are noted for production.

**Rejected:**
- *Separate upload endpoint then create call:* two round trips and a cleanup problem for abandoned uploads.
- *Generic PATCH/PUT of the whole lead:* lets callers change fields they should not.
- *CAPTCHA and rate limiting now:* adds third-party dependencies and complexity before there is traffic to protect against.

## Duplicate leads: Proposed
- No unique constraint on email, so a prospect can resubmit; the list shows newest first.

**Why:** Rejecting a resubmission would block a legitimate prospect who corrected details or sent a new resume, and a unique constraint on a public form also reveals whether an email already exists. Showing newest first lets attorneys see the latest submission.

**Rejected:**
- *Unique email constraint:* loses updates and leaks existence of prior submissions.
- *Upsert on email:* silently overwrites history and lets anyone overwrite another person's lead by typing their email.

## Layering: Decided
- `routers -> services -> data_acceses -> models`, with no business logic in routers (see `CLAUDE.md`).

**Why:** Strict downward dependencies keep business rules testable without HTTP or a database, and make the SQLite-to-Postgres and email-provider swaps local changes.

**Rejected:**
- *Logic in routers or queries in services:* faster to write initially, but couples rules to the framework and makes tests heavier.

## Lead model and data access: Decided (implementation choices not in the design)
- `Lead` has a UUID string `id`, `resume_path` (a storage key, not a public path), and `reached_out_by` (the attorney's email, set from the auth token). `state` is stored as a string, not a native DB enum. Timestamps are timezone-aware UTC.
- Only the requested fields are stored. Resume filename, content type and size are not, and there is no `updated_at`; add them when a feature needs them.
- `LeadDataAccess` flushes on `add` and exposes `commit()`. It has `add`, `get_by_id`, `list` (newest first, optional state filter, limit/offset) and `count`. Transition rules are not in it; they belong in the service.
- Tables are created with `create_all` at app startup for now. `Base` lives in `models/base.py` so models and tests never import settings or an engine.

**Why:** A UUID id is not guessable in URLs. Naming the field `resume_path` but treating it as a key keeps the storage backend swappable. Storing the state as a string avoids a native enum that SQLite ignores and that Alembic handles awkwardly. `reached_out_by` was in the approved design and the auth rule says it must come from the token, so the column exists even though it was not in the field list. Flush-then-`commit()` lets a service later save a lead and its `email_events` rows in one transaction, which the email-tracking decision requires. `create_all` is enough while the schema is one table and SQLite is the target. Keeping `Base` separate means data-access tests run on an in-memory database with no env file.

**Rejected:**
- *Autoincrement integer id:* guessable, which matters because ids appear in internal URLs.
- *Data access commits inside every method:* would make the lead and its email rows two transactions.
- *`mark_reached_out()` on the data-access class:* a state transition is a business rule, so it stays in the service.
- *Alembic now:* correct once the schema changes over time, but pure overhead for the first table. Revisit before the second migration.
- *Storing resume filename, size and content type now:* not needed by any requirement yet.

## Lead schemas: Decided (implementation choices not in the design)
- `LeadCreate` holds only first name, last name and email; the resume arrives as a multipart file, not in JSON. `LeadCreate` and `LeadUpdate` forbid extra fields, and `LeadUpdate` accepts only `REACHED_OUT`.
- `LeadRead` omits `resume_path`; the resume is fetched through the authenticated download endpoint.
- Names are stripped of surrounding whitespace and capped at 100 characters; email is validated with `EmailStr`, which adds the `email-validator` dependency (`pydantic[email]`).

**Why:** `extra="forbid"` makes the "identity never in a request body" rule enforceable: a client sending a `user` or `reached_out_by` field gets a 422 instead of being silently ignored. Hiding `resume_path` stops the internal storage layout leaking to the API. Validating email syntax at the edge catches typos before they become undeliverable confirmation emails. The new dependency is the standard, maintained way to do that in Pydantic.

**Rejected:**
- *Ignoring unknown fields:* hides client mistakes and weakens the auth rule.
- *Returning `resume_path` in `LeadRead`:* exposes storage details for no benefit.
- *A hand-written email regex:* easy to get wrong and no cheaper than the library.

## Data-access naming: Decided
- Classes in `data_acceses/` are named `<Entity>DataAccess` in `<entity>_data_access.py` (e.g. `LeadDataAccess`), not "Repository".

**Why:** The layer is called data access, so its classes should say the same; a reader can tell where a class belongs from its name.

**Rejected:**
- *`LeadRepository`:* a valid pattern name, but it did not match the layer name and read as a different concept.
