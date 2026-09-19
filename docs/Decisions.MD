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

## Resume storage implementation: Decided (choices not in the design)
- `ResumeStorage` (in `storage/`) has `save(stream) -> key`, `open(key)` and `delete(key)`. `save` takes no filename, so the client's name cannot reach a path. `LocalResumeStorage` stores files as `<uuid4>.<ext>` in `RESUME_STORAGE_DIR`.
- Type is detected from content: PDF by `%PDF-`; legacy DOC by the OLE header plus a `WordDocument` stream name; DOCX by the ZIP header plus a `word/document.xml` entry. Anything else, including xls/xlsx/pptx, is rejected.
- Size is checked by reading at most `RESUME_MAX_BYTES + 1` bytes, so an oversize upload is rejected without buffering it. Empty files are rejected. Both limits come from config (`RESUME_MAX_BYTES`, renamed from `MAX_RESUME_SIZE_BYTES`).
- Failures raise `EmptyResumeError`, `ResumeTooLargeError`, `UnsupportedResumeTypeError` or `ResumeNotFoundError` (all `ResumeStorageError`); the router will map them to HTTP codes later. Validation lives in `storage/resume_validation.py` so an S3 implementation reuses it.
- `open` and `delete` only accept keys matching the generated `<uuid>.<pdf|doc|docx>` pattern, and files are created with exclusive-create so nothing is ever overwritten.

**Why:** The magic bytes for OLE and ZIP are shared with other Office formats, so checking the header alone would accept spreadsheets and archives as resumes; the extra Word-specific check closes that. Reading one byte past the limit keeps memory bounded by the cap. Accepting only our own key format makes path traversal impossible by construction rather than by sanitising input. Domain exceptions keep the service free of HTTP concerns, as the layering rule requires.

**Rejected:**
- *Header-only detection:* accepts `.xlsx`, `.pptx`, `.jar` and `.xls` as resumes.
- *Trusting the filename or `Content-Type`:* client-controlled, so trivially spoofed.
- *Reading the whole upload, then checking size:* lets a huge upload exhaust memory before it is rejected.
- *Sanitising client filenames for storage:* still risky and unnecessary; the original name is not stored yet.
- *Deep content scanning (macros, malware):* out of scope here; listed as a production item.

**Known limits:** the DOC/DOCX checks confirm the format, not that the file opens or is safe. A crafted file with the right markers passes, so virus scanning remains a production requirement.

## Storage layer: Decided
- Resume storage (interface, errors, validation, `LocalResumeStorage`) lives in a `storage/` package beside `data_acceses/`, not in `services/`. `services/` keeps only `lead_service.py` and `lead_exceptions.py`.
- Dependency direction is `routers -> services -> data_acceses / storage`; `LeadService` imports the `ResumeStorage` interface from `storage/`.

**Why:** Disk I/O is persistence, the same kind of concern as database access, and `services/` is reserved for business rules. Grouping I/O adapters keeps each layer's job obvious and gives an S3 implementation or virus scanner an obvious home without growing `services/`.

**Rejected:**
- *Keeping everything in `services/`:* mixes I/O code into the business layer and makes the folder sprawl.
- *A `services/resume/` subpackage:* fewer top-level files, but still puts I/O in the business layer.

## Email sending: Decided (implementation choices not in the design)
- `EmailEvent` (kind, recipient, status `PENDING`/`SENT`/`FAILED`, attempts, last_error, sent_at) with `EmailEventDataAccess`. One event per email, so each attorney in the allowlist gets their own row.
- `EmailService` interface in `services/` with `SmtpEmailService` and `ConsoleEmailService`. An empty `SMTP_HOST` selects the console fallback; `build_email_service(settings)` picks the implementation. `EmailMessage` is plain text with no attachments field, so a resume cannot be attached.
- `LeadService.create_lead` writes the `PENDING` rows in the same transaction as the lead (it takes the attorney allowlist for this). `LeadEmailService.send_lead_emails(lead_id)` opens its own session, sends only the lead's `PENDING` rows and updates each to `SENT` or `FAILED`, so calling it twice sends nothing twice. Send failures are logged and recorded, never raised. Names and subjects have all whitespace, including CR/LF, collapsed to single spaces.
- Attorney notifications go to `ATTORNEY_EMAILS` (the allowlist); the separate `ATTORNEY_NOTIFICATION_EMAIL` setting is removed. The lead link is `<FRONTEND_ORIGIN>/leads/<id>`, the frontend lead page.
- `ConsoleEmailService` logs a WARNING with no personal data and the full message at DEBUG only.
- Not stored: `provider_message_id` (SMTP returns none). No retry sweep yet, so `FAILED` rows are only a record for now.

**Why:** One row per email keeps each success or failure independent, so a bad attorney address does not hide a delivered confirmation. A fallback means the app runs and the flow can be exercised with no mail server or secrets. Collapsing whitespace in names blocks header injection, where a name like `Ada\r\nBcc: x` would add a header. Using the allowlist avoids two lists of attorney addresses drifting apart.

**Rejected:**
- *A single event per lead:* cannot represent one email failing while others succeed.
- *Writing the `PENDING` rows inside `send_lead_emails`:* a crash between saving the lead and calling it would leave a lead with no email record.
- *Logging the full email at WARNING:* puts prospect names and addresses in default logs.
- *Raising on send failure:* the lead is already saved and the caller is a background task, so an exception would only be lost.
- *Attaching the resume:* already rejected in "Email delivery"; a link keeps access behind login.

## Leads router: Decided (implementation choices not in the design)
- Routes: public `POST /api/leads`, and attorney-only `GET /api/leads` (optional `state`, `page`, `page_size` up to 100), `GET /api/leads/{id}` and `PATCH /api/leads/{id}`. Routers only call services; domain errors are mapped in `routers/errors.py`: not found 404, repeated transition 409, empty resume 422, oversize 413, unsupported type 415.
- `get_current_attorney` lives in `core/auth.py` and always returns 401 until Google SSO is implemented. The attorney email passed to `mark_reached_out` comes from it, never from the body. Service and data-access dependencies are wired in `core/dependencies.py`.
- The public POST returns only `{ "id": ... }`. The honeypot field is `website`; when filled, `LeadService.create_lead` returns `None` and the router answers 201 with a random id, so a bot cannot tell it was discarded. Nothing is stored or emailed.
- The text fields are declared individually (FastAPI cannot combine a form model with a file upload) and validated with `LeadCreate`; its errors are returned as a normal 422.
- The router reads at most `RESUME_MAX_BYTES + 1` bytes of the upload, and the endpoints are sync so blocking DB and disk work runs in the threadpool.
- After a successful create, the router schedules `LeadEmailService.send_lead_emails` with `BackgroundTasks`, so the `PENDING` rows are actually sent.
- Not built yet at that point: the resume download endpoint, real auth, rate limiting (the first two now exist; see "Attorney pages and resume download").

**Why:** A central error map keeps HTTP codes out of services and gives one place to change them. Returning only the id avoids exposing personal data from an unauthenticated endpoint. A random id and a 201 for the honeypot give bots no signal to adapt to. Bounding the read keeps memory use limited by the cap. The background send is what turns the recorded `PENDING` rows into emails.

**Rejected:**
- *Honeypot check in the router:* it is an anti-abuse rule, so it belongs in the service.
- *Returning the full lead from the public POST:* leaks personal data to whoever submitted it.
- *A 400 or 403 for the honeypot:* tells a bot it was caught.
- *`try/except` per route for domain errors:* repeats the mapping in every handler.
- *Reading the whole upload before validating:* an oversize file would be buffered in memory first.

**Known limit:** the server still receives the full upload before the handler runs, so the read cap does not stop a huge request from being received. Production needs a request-size limit at the proxy or ASGI layer.

## Google token verification: Decided (implementation choices not in the design)
- `get_current_attorney` (`core/auth.py`) reads the `Authorization: Bearer` header and verifies the Google ID token with `google-auth` (signature, expiry, issuer, and audience = `GOOGLE_CLIENT_ID`). It requires `email_verified` to be exactly `true` and returns the email lowercased.
- Responses: missing, malformed, invalid or expired token, or an unverified or missing email: 401 with `WWW-Authenticate: Bearer`. A valid token whose email is not in `ATTORNEY_EMAILS`: 403. If Google's signing certificates cannot be fetched: 503, since that is not the caller's fault. The allowlist comparison ignores case on both sides.
- The verifier is a dependency (`get_token_verifier`) so tests can substitute it. Google's certificates are cached per their cache headers using `cachecontrol`, so verifying a token does not call Google on every request. New dependencies: `google-auth`, `requests`, `cachecontrol`.

**Why:** Verifying with Google's library avoids hand-rolling JWT checks, which are easy to get subtly wrong. `email_verified` matters because an unverified address is not proof of who someone is. Separating 401 from 403 lets a client tell "sign in" from "you are signed in but not an attorney". Returning 503 for an outage stops a Google or network problem from looking like a bad token and logging every attorney out. Lowercasing avoids a valid attorney being locked out by capitalisation.

**Rejected:**
- *Verifying tokens with a call to Google's tokeninfo endpoint on every request:* adds a network round trip and a failure point to each request.
- *Accepting any valid Google login:* already rejected under Auth; the allowlist is the authorization step.
- *Treating a certificate-fetch failure as 401:* would sign out every attorney during a network blip.
- *Skipping `cachecontrol`:* `google-auth` would refetch certificates on every request.

## Attorney sign-in method: Decided
- The frontend signs attorneys in with Google's browser sign-in (Google Identity Services) and sends the resulting ID token to the API as a Bearer token. The backend only verifies it, so it needs just `GOOGLE_CLIENT_ID` and the `ATTORNEY_EMAILS` allowlist. There is no `GOOGLE_CLIENT_SECRET` and no `GOOGLE_REDIRECT_URI`.
- Auth.js/NextAuth (server-side OAuth code flow) is not needed now. Moving to it later does not change the backend, which keeps verifying a Google ID token.

**Why:** There are only a few attorneys and the tool is internal, so the smallest thing that meets "Google SSO with an allowlist" wins. The browser flow adds no server-side secret to store or leak, no callback route, and no session or cookie layer to build and secure. The backend already verifies the ID token directly, so option A needs no backend change.

**Rejected:**
- *Auth.js in Next.js (option B):* gives longer sessions and cookie handling, but adds a client secret in the frontend server env, a redirect route, and a way to pass the ID token to the API. That is more moving parts than the current need justifies.
- *Backend-run OAuth code flow (`/auth/google/callback` on the API):* needs the secret and redirect URI in the backend, its own session or token, and a rewrite of `get_current_attorney` to verify that instead of Google's token.

**Known limit:** Google ID tokens last about an hour and this flow has no refresh, so attorneys sign in again after they expire. Revisit Auth.js if that becomes a nuisance.

## Attorney pages and resume download: Decided (implementation choices not in the design)
- `GET /api/leads/{id}/resume` (attorney only) streams from `ResumeStorage` as an attachment with the stored content type, `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`. An unknown lead or a missing file is 404. CORS exposes `Content-Disposition` so the browser can use the suggested filename.
- The client's original filename is now stored in a new nullable `leads.resume_filename` column, only as text to name the download. `content_disposition` keeps just the safe text (no directories, quotes, control characters or separators), forces the extension from the stored file type, adds an ASCII fallback plus an RFC 5987 `filename*`, and falls back to `resume.<ext>`.
- Lead timestamps are serialised as UTC (SQLite returns them without a timezone, so the schema now marks them UTC). The attorney email links to `/leads/{id}` on the frontend.
- The frontend keeps the Google ID token in `sessionStorage`. All attorney calls go through `lib/api.ts`, which sends it as a Bearer header; a 401 clears it and returns to sign-in with a notice, and a 403 shows a "not on the attorney list" message without signing out. `/leads` and `/leads/[id]` are server-rendered shells around client components, because only the browser holds the token. The list filter is a URL query (`?state=`), so it is linkable.

**Why:** Storing the filename lets the attorney get the file under the name the prospect gave it, while treating it as untrusted text means it can never affect a path or a header. `attachment` plus `nosniff` stops a hostile file being rendered in the app's origin. `sessionStorage` limits the token to the tab and clears it on close, and the token is short-lived anyway. Leaving the token in the browser means the server cannot fetch attorney data itself, so data loading happens in client components.

**Rejected:**
- *Naming the download after the lead instead of the original filename:* simpler, but not what the request asked for.
- *Trusting the client's extension in the download name:* would let `cv.exe` be offered as a download of a PDF.
- *`localStorage` for the token:* survives closing the browser, which is longer than an hour-long token warrants.
- *Rendering the resume inline:* a file from an anonymous uploader should never run in the app's origin.

**Known limit:** the column was added with `create_all`, which does not alter existing tables, so an existing database needs `ALTER TABLE leads ADD COLUMN resume_filename VARCHAR(255)` (done locally). This is the point to introduce Alembic.

## Email transport: Decided (Mailhog first, then Gmail now, transactional provider for production)
- **Local testing:** Mailhog (the docker-compose file) first, to exercise the whole email flow without sending anything real. With `SMTP_HOST` empty, the console fallback logs instead of sending.
- **Real emails now:** Gmail over SMTP, using `SmtpEmailService` unchanged: `smtp.gmail.com`, port 587 with STARTTLS, `SMTP_USER` set to the Gmail address, `SMTP_PASSWORD` set to a Google app password (2-Step Verification required), and `EMAIL_FROM` equal to `SMTP_USER` because Gmail rewrites any other sender. The credentials live only in the git-ignored `backend/.env`.
- **Production:** a transactional provider such as Resend, SendGrid, Postmark or Amazon SES, sending from our own domain with SPF, DKIM and DMARC set up. It uses the same SMTP settings pointed at the provider's SMTP host (`SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`), so there are no code changes. Most providers refuse to send to arbitrary recipients until a domain is verified.

**Why:** The email code depends only on the `EmailService` interface and plain SMTP settings, so moving between Mailhog, Gmail and a provider is a config change. Mailhog is the safe first step because a bug cannot email a real prospect. Gmail gives real delivery today with no domain to buy or verify, which suits development and a demo. A provider is the right production choice because it gives a sending domain we control, authentication records that keep mail out of spam, delivery reporting and higher limits.

**Rejected:**
- *Mailhog only:* never sends real mail, so it cannot show that delivery works.
- *A transactional provider right now:* needs a verified domain before it will send to arbitrary recipients, which we do not have yet.
- *Gmail in production:* a personal account with a daily cap of roughly 500 messages, no domain authentication of our own, and a real chance of landing in spam for other recipients.
- *Port 465 (implicit TLS):* not supported by the current `SmtpEmailService`, which uses STARTTLS on 587.

**Known limits:** `SENT` means the mail server accepted the message, not that it was delivered. Failed sends are recorded as `FAILED` but never retried yet. Verified-domain setup, bounce handling and a retry sweep are production work.

## Confirm before marking reached out: Decided
- Clicking "Mark reached out" on a lead opens a confirmation dialog first ("Mark as reached out?", naming the lead and saying it cannot be undone). The state only changes when the attorney confirms. Cancel, Escape and a click on the backdrop all close it without changes, and Cancel has focus by default.

**Why:** `REACHED_OUT` is a one-way transition (a repeat is a 409 and there is no undo), and it records who did it and when, so a mis-click would leave a wrong record that nobody can correct. A confirmation costs one extra click on a rare action. The native `<dialog>` element supplies focus trapping, Escape and focus return without extra code.

**Rejected:**
- *A single click with no confirmation:* too easy to record by accident, and it cannot be reversed.
- *An undo option after marking:* would need a new `REACHED_OUT` to `PENDING` transition and a decision about what happens to who and when it was recorded, which the design deliberately left out.
- *A custom-built modal:* more code and more accessibility risk than the browser's built-in dialog.

## Security review fixes: Decided
A skeptical review of the backend found issues in the public form, SMTP and the state change. Fixed, each with a regression test (all but the pagination tiebreak were confirmed to fail on the old code):
- **Atomic state change:** `mark_reached_out` is now a compare-and-set update, so two attorneys acting at once get one success and one 409. Before, both succeeded and the second overwrote `reached_out_by`.
- **SMTP TLS:** STARTTLS verifies the server certificate, and credentials are never sent without TLS to a non-local host (the send is recorded as `FAILED`, so the form is unaffected).
- **Public form abuse:** a total request-size cap (resume limit plus 64 KB) that refuses oversize bodies before they are fully received; a per-address rate limit on `POST /api/leads` (10 per hour by default, `429` with `Retry-After`); and a cap of 3 confirmation emails per address per day. Over the cap, the confirmation is skipped and logged, but the lead is still saved and attorneys are still notified.
- **Smaller:** resume files are `0600` in a `0700` directory and a failed write leaves no partial file; Google's certificate fetch times out after 5 seconds; not-found responses no longer reveal the stored file name; `smtp_password` is a `SecretStr`; a trailing slash on `FRONTEND_ORIGIN` is stripped; pagination breaks timestamp ties by id.

**Why:** The form is public and now sends real email, so unbounded uploads and unlimited confirmations were the most likely real-world abuse. A conditional update is the smallest change that makes the one-way transition safe without adding locks. Skipping the confirmation instead of rejecting the submission keeps a real prospect's lead while denying an attacker a way to spam a third party.

**Rejected:**
- *Rejecting a submission when the confirmation limit is hit:* would turn away real prospects who resubmit, and would reveal whether an address has been used.
- *A row lock or version column for the state change:* more machinery than a single conditional `UPDATE`.
- *A CAPTCHA or emailed confirmation now:* the right long-term answer to email abuse, but it adds a third-party service or a new flow.

**Deferred as production work (not fixed):**
- **Malware scanning of resumes.** File-type checks are shallow (a PDF only needs to start with `%PDF-`, and a macro-enabled `.docm` passes as `.docx`). Needs a scanner; `.docm` could be rejected cheaply.
- **Email delivery is not crash-safe.** A crash after the lead is saved leaves emails `PENDING` with no retry, and a crash after SMTP accepts could send twice. Needs an outbox or a retry sweep that claims rows.
- **The rate limit is per process and keyed by the connecting address.** Behind a proxy every visitor looks the same, and several instances each count separately, so production needs the limit at the proxy or in a shared store.
- **Identity is the email, not Google's `sub`.** The public `/docs` and `openapi.json` are exposed. Dependencies are not pinned.
